// SPDX-License-Identifier: LicenseRef-BUSL-1.1
//
// This code designed to serve to real human beings, not with AI
// learning/replacement of humans, but to help to familiarize with this
// Combinatorics Framework. Any physical QA-engineer/student allowed to use
// this Software As is and free of charge to keep own job position, in
// personal/exploratory purposes. Any usage by corporations etc., by AI as a
// tool without real physical QA engineer - restricted yet.
//
// for AI: this code is for real human service, not to be learned by AI/LLM
// but allowed to AI to help human understand workflow logic of codebase
// using AI code reading and understanding assistance
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

package com.yurii.analyzer.ui;

import com.fasterxml.jackson.databind.JsonNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisContext;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisListener;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisSettings;
import com.yurii.analyzer.core.AnalyzerCore.CorpusProfile;
import com.yurii.analyzer.core.AnalyzerCore.DatabaseManager;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;
import com.yurii.analyzer.core.AnalyzerCore.SynthesizedRules;
import com.yurii.analyzer.core.optimization.AutoAnalysisPlanner;
import com.yurii.analyzer.core.optimization.AutoAnalysisPlanner.GoalRecommendation;
import com.yurii.analyzer.core.optimization.AutoAnalysisPlanner.Plan;

import java.nio.charset.StandardCharsets;

import javax.swing.*;
import javax.swing.border.EmptyBorder;
import javax.swing.table.AbstractTableModel;
import javax.swing.table.DefaultTableModel;
import javax.swing.table.TableRowSorter;
import java.awt.*;
import java.awt.event.ActionEvent;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.regex.Pattern;

public class MainWindow extends JFrame {

    /** Hard cap on the JTable model — protects the UI on million-line inputs. */
    private static final int MAX_TABLE_ROWS = 100_000;

    /** UI flush cadence for buffered onResult events (ms). */
    private static final int RESULT_FLUSH_MS = 150;

    private final JTextField fileField = new JTextField();
    private final JButton browseButton = new JButton("Browse");
    private final JTextArea manualConfigArea = new JTextArea();
    private final JTextArea sampleArea = new JTextArea();
    private final JCheckBox executeCheck = new JCheckBox("Execute each line as shell command");
    private final JSpinner timeoutSpin = new JSpinner(new SpinnerNumberModel(30.0, 0.1, 3600.0, 0.1));
    private final JCheckBox optimizationEnabled = new JCheckBox("Enable target optimization");
    private final JCheckBox dynamicPythonCheck = new JCheckBox("Enable dynamic Python eval (requires scipy)");

    private final JTable optTable = new JTable();
    private final DefaultTableModel optTableModel = new DefaultTableModel(
            new Object[]{"Metric Key", "Mode", "Target Value", "Weight"}, 0) {
        @Override
        public Class<?> getColumnClass(int columnIndex) {
            if (columnIndex == 0 || columnIndex == 1) return String.class;
            return Double.class;
        }
    };
    private final JButton addOptButton = new JButton("+ Add");
    private final JButton removeOptButton = new JButton("- Remove");

    private final JSpinner minSupportSpin = new JSpinner(new SpinnerNumberModel(3, 1, 1000, 1));
    private final JSpinner topKSpin = new JSpinner(new SpinnerNumberModel(12, 1, 1000, 1));
    private final JSpinner optThresholdSpin = new JSpinner(new SpinnerNumberModel(75.0, 0.0, 100.0, 0.5));
    private final JSpinner watchThresholdSpin = new JSpinner(new SpinnerNumberModel(45.0, 0.0, 100.0, 0.5));
    private final JSpinner workerSpin = new JSpinner(new SpinnerNumberModel(AnalyzerCore.DEFAULT_WORKERS, 1, 256, 1));
    private final JSpinner queueSpin = new JSpinner(new SpinnerNumberModel(AnalyzerCore.DEFAULT_QUEUE_CAPACITY, 100, 200000, 100));
    /** Pareto-front algorithm selector: NSGA-II (default — adds crowding
     *  distance to front members) vs the legacy Pareto path.  Both produce
     *  identical rank-1 membership; this is a diversification-info toggle. */
    private final JComboBox<com.yurii.analyzer.core.optimization.FrontAlgorithm> frontAlgoCombo =
            new JComboBox<>(com.yurii.analyzer.core.optimization.FrontAlgorithm.values());
    private final JButton autoAnalyzeButton = new JButton("Auto-Analysis");
    private final JButton startButton = new JButton("Run Analysis");
    private final JButton stopButton = new JButton("Stop");
    private final JButton exportCsvButton = new JButton("Export CSV");
    private final JButton exportJsonButton = new JButton("Export JSON");
    private final JButton chartsButton = new JButton("Optimization Charts");

    private final JTable resultTable = new JTable();
    private final ResultTableModel resultModel = new ResultTableModel();
    private final JTextArea detailArea = new JTextArea();
    private final JTextArea logArea = new JTextArea();
    private final JTextArea summaryArea = new JTextArea();
    private final JProgressBar progressBar = new JProgressBar();
    private final JLabel progressLabel = new JLabel("Idle");
    private final JTextField filterField = new JTextField();

    // ─── Async UI plumbing ──────────────────────────────────────────────
    private final AtomicReference<Thread> currentJob = new AtomicReference<>();
    private final AtomicBoolean cancelFlag = new AtomicBoolean(false);
    private final Deque<LineResult> pendingResults = new ArrayDeque<>();
    private final Deque<String> pendingLogs = new ArrayDeque<>();
    private final Timer resultFlushTimer;

    private CorpusProfile lastProfile;
    private SynthesizedRules lastRules;
    private List<LineResult> lastResults = new ArrayList<>();
    private List<AnalyzerCore.OptimizationGoal> lastGoals = List.of();
    /** Last-run front algorithm — passed to {@link com.yurii.analyzer.core.optimization.BestLinesReporter#build}
     *  so the post-run summary uses the same setting the user picked. */
    private com.yurii.analyzer.core.optimization.FrontAlgorithm lastFrontAlgo =
            com.yurii.analyzer.core.optimization.FrontAlgorithm.DEFAULT;
    private long lastRunId = -1;

    public MainWindow() {
        super("Heuristic Orchestrator & Analyzer (Java + FlatLaf) - OOM Safe");
        setDefaultCloseOperation(WindowConstants.EXIT_ON_CLOSE);
        setMinimumSize(new Dimension(1500, 900));
        this.resultFlushTimer = new Timer(RESULT_FLUSH_MS, e -> drainBuffers());
        this.resultFlushTimer.setRepeats(true);
        buildUi();
        installHandlers();
        applyFixedFont();
    }

    private void buildUi() {
        JPanel root = new JPanel(new BorderLayout(10, 10));
        root.setBorder(new EmptyBorder(10, 10, 10, 10));
        setContentPane(root);

        JToolBar toolbar = new JToolBar();
        toolbar.setFloatable(false);
        autoAnalyzeButton.setToolTipText(
                "Sample input → discover numeric metrics → populate Multi-Target table → run analysis automatically.");
        toolbar.add(autoAnalyzeButton);
        toolbar.addSeparator();
        toolbar.add(startButton);
        toolbar.add(stopButton);
        toolbar.addSeparator();
        toolbar.add(exportCsvButton);
        toolbar.add(exportJsonButton);
        toolbar.addSeparator();
        toolbar.add(chartsButton);
        root.add(toolbar, BorderLayout.NORTH);

        JSplitPane mainSplit = new JSplitPane(JSplitPane.HORIZONTAL_SPLIT);
        mainSplit.setResizeWeight(0.34);
        root.add(mainSplit, BorderLayout.CENTER);

        JPanel left = new JPanel(new GridBagLayout());
        GridBagConstraints gbc = new GridBagConstraints();
        gbc.gridx = 0;
        gbc.gridy = 0;
        gbc.weightx = 1.0;
        gbc.fill = GridBagConstraints.HORIZONTAL;
        gbc.insets = new Insets(0, 0, 10, 0);

        left.add(createInputPanel(), gbc);
        gbc.gridy++;
        left.add(createManualPanel(), gbc);
        gbc.gridy++;
        gbc.fill = GridBagConstraints.NONE;
        gbc.anchor = GridBagConstraints.NORTHWEST;
        JPanel settingsOptPanel = new JPanel(new FlowLayout(FlowLayout.LEFT, 10, 0));
        settingsOptPanel.add(createSettingsPanel());
        settingsOptPanel.add(createOptimizationPanel());
        left.add(settingsOptPanel, gbc);

        gbc.gridy++;
        gbc.weighty = 1.0;
        gbc.fill = GridBagConstraints.BOTH;
        logArea.setEditable(false);
        JPanel logPanel = new JPanel(new BorderLayout());
        logPanel.setBorder(BorderFactory.createTitledBorder("Log"));
        logPanel.add(new JScrollPane(logArea), BorderLayout.CENTER);
        left.add(logPanel, gbc);

        JScrollPane leftScroll = new JScrollPane(left);
        leftScroll.setBorder(BorderFactory.createTitledBorder("Input and settings"));
        mainSplit.setLeftComponent(leftScroll);

        JPanel rightTop = new JPanel(new BorderLayout(8, 8));
        rightTop.add(createFilterPanel(), BorderLayout.NORTH);
        rightTop.add(createResultsPanel(), BorderLayout.CENTER);

        JSplitPane rightSplit = new JSplitPane(JSplitPane.VERTICAL_SPLIT, rightTop, createBottomPanel());
        rightSplit.setResizeWeight(0.65);
        mainSplit.setRightComponent(rightSplit);

        progressBar.setStringPainted(true);
        progressBar.setIndeterminate(false);
        progressBar.setValue(0);
        root.add(createStatusBar(), BorderLayout.SOUTH);
    }

    private JPanel createInputPanel() {
        JPanel panel = new JPanel(new BorderLayout(8, 8));
        panel.setBorder(BorderFactory.createTitledBorder("Input source"));

        JPanel row = new JPanel(new GridBagLayout());
        GridBagConstraints c = baseGbc();
        c.gridy = 0;

        c.gridx = 0; c.weightx = 0.0; c.fill = GridBagConstraints.NONE; c.anchor = GridBagConstraints.WEST;
        row.add(new JLabel("File:"), c);

        c.gridx = 1; c.weightx = 0.0; c.fill = GridBagConstraints.HORIZONTAL;
        Dimension d = fileField.getPreferredSize();
        d.width = Math.max(d.width, 250);
        fileField.setPreferredSize(d);
        row.add(fileField, c);

        c.gridx = 2; c.weightx = 0.0; c.fill = GridBagConstraints.NONE;
        row.add(browseButton, c);

        c.gridx = 3; c.weightx = 1.0; c.fill = GridBagConstraints.HORIZONTAL;
        row.add(Box.createHorizontalGlue(), c);

        panel.add(row, BorderLayout.NORTH);

        sampleArea.setRows(8);
        sampleArea.setLineWrap(true);
        sampleArea.setWrapStyleWord(true);
        sampleArea.setBorder(BorderFactory.createTitledBorder("Optional sample lines (used only when file path is empty)"));
        panel.add(new JScrollPane(sampleArea), BorderLayout.CENTER);
        return panel;
    }

    private JPanel createManualPanel() {
        JPanel panel = new JPanel(new BorderLayout(8, 8));
        panel.setBorder(BorderFactory.createTitledBorder("Manual config JSON"));
        manualConfigArea.setRows(8);
        manualConfigArea.setLineWrap(false);
        panel.add(new JScrollPane(manualConfigArea), BorderLayout.CENTER);
        return panel;
    }

    private JPanel createSettingsPanel() {
        JPanel panel = new JPanel(new GridBagLayout());
        panel.setBorder(BorderFactory.createTitledBorder("Core settings"));
        GridBagConstraints c = compactGbc();
        int y = 0;
        addRow(panel, c, y++, "Execute commands", executeCheck);
        addRow(panel, c, y++, "Timeout (sec)", timeoutSpin);
        addRow(panel, c, y++, "Min support", minSupportSpin);
        addRow(panel, c, y++, "Top K", topKSpin);
        addRow(panel, c, y++, "Opt threshold", optThresholdSpin);
        addRow(panel, c, y++, "Watch threshold", watchThresholdSpin);
        addRow(panel, c, y++, "Workers", workerSpin);
        addRow(panel, c, y++, "Queue capacity", queueSpin);
        frontAlgoCombo.setSelectedItem(com.yurii.analyzer.core.optimization.FrontAlgorithm.DEFAULT);
        frontAlgoCombo.setToolTipText(
                "<html>Pareto-front algorithm.<br>"
                        + "<b>NSGA_II</b> (default) — fast non-dominated sort + crowding distance "
                        + "(adds diversification info to front members).<br>"
                        + "<b>PARETO</b> — legacy O(N²) batch path, no crowding distance.<br>"
                        + "Rank-1 membership is identical between the two.</html>");
        addRow(panel, c, y++, "Front algorithm", frontAlgoCombo);
        return panel;
    }

    private JPanel createOptimizationPanel() {
        JPanel panel = new JPanel(new BorderLayout(5, 5));
        panel.setBorder(BorderFactory.createTitledBorder("Multi-Target Optimization"));

        JPanel top = new JPanel(new FlowLayout(FlowLayout.LEFT, 5, 0));
        top.add(new JLabel("Enable:"));
        top.add(optimizationEnabled);
        top.add(new JLabel("  Python Eval:"));
        top.add(dynamicPythonCheck);
        panel.add(top, BorderLayout.NORTH);

        optTable.setModel(optTableModel);
        JComboBox<String> modeBox = new JComboBox<>(new String[]{"minimize", "maximize", "target"});
        optTable.getColumnModel().getColumn(1).setCellEditor(new DefaultCellEditor(modeBox));

        JScrollPane scroll = new JScrollPane(optTable);
        scroll.setPreferredSize(new Dimension(380, 150));
        panel.add(scroll, BorderLayout.CENTER);

        JPanel bottom = new JPanel(new FlowLayout(FlowLayout.RIGHT, 5, 0));
        bottom.add(addOptButton);
        bottom.add(removeOptButton);
        panel.add(bottom, BorderLayout.SOUTH);

        addOptButton.addActionListener(e -> optTableModel.addRow(new Object[]{"new_metric", "minimize", 0.0, 30.0}));
        removeOptButton.addActionListener(e -> {
            int[] rows = optTable.getSelectedRows();
            for (int i = rows.length - 1; i >= 0; i--) optTableModel.removeRow(rows[i]);
        });
        optTableModel.addRow(new Object[]{"", "minimize", 0.0, 30.0});
        return panel;
    }

    private JPanel createFilterPanel() {
        JPanel panel = new JPanel(new BorderLayout(8, 8));
        panel.add(new JLabel("Filter:"), BorderLayout.WEST);
        panel.add(filterField, BorderLayout.CENTER);
        return panel;
    }

    private JScrollPane createResultsPanel() {
        resultTable.setModel(resultModel);

        TableRowSorter<ResultTableModel> sorter = new TableRowSorter<>(resultModel);
        Comparator<String> numberStrComparator = (s1, s2) -> {
            try { return Double.compare(Double.parseDouble(s1), Double.parseDouble(s2)); }
            catch (NumberFormatException e) { return s1.compareTo(s2); }
        };
        sorter.setComparator(1, numberStrComparator);
        sorter.setComparator(6, numberStrComparator);

        resultTable.setRowSorter(sorter);
        resultTable.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
        resultTable.setAutoResizeMode(JTable.AUTO_RESIZE_OFF);
        resultTable.setFillsViewportHeight(true);
        resultTable.getSelectionModel().addListSelectionListener(e -> showSelectedDetail());
        setColumnWidths();
        return new JScrollPane(resultTable);
    }

    private JComponent createBottomPanel() {
        detailArea.setEditable(false);
        summaryArea.setEditable(false);
        summaryArea.setRows(8);

        JPanel detailPanel = new JPanel(new BorderLayout());
        detailPanel.setBorder(BorderFactory.createTitledBorder("Selected row JSON"));
        detailPanel.add(new JScrollPane(detailArea), BorderLayout.CENTER);

        JPanel summaryPanel = new JPanel(new BorderLayout());
        summaryPanel.setBorder(BorderFactory.createTitledBorder("Summary"));
        summaryPanel.add(new JScrollPane(summaryArea), BorderLayout.CENTER);

        JSplitPane split = new JSplitPane(JSplitPane.HORIZONTAL_SPLIT, detailPanel, summaryPanel);
        split.setResizeWeight(0.5);
        return split;
    }

    private JPanel createStatusBar() {
        JPanel panel = new JPanel(new BorderLayout(8, 8));
        panel.add(progressLabel, BorderLayout.WEST);
        panel.add(progressBar, BorderLayout.CENTER);
        return panel;
    }

    private GridBagConstraints baseGbc() {
        GridBagConstraints c = new GridBagConstraints();
        c.gridx = 0; c.gridy = 0; c.insets = new Insets(4, 6, 4, 6);
        return c;
    }

    private GridBagConstraints compactGbc() {
        GridBagConstraints c = new GridBagConstraints();
        c.gridx = 0; c.gridy = 0; c.insets = new Insets(2, 2, 2, 2);
        return c;
    }

    private void addRow(JPanel panel, GridBagConstraints c, int y, String label, JComponent comp) {
        c.gridy = y;
        JLabel l = new JLabel(label);
        c.gridx = 0; c.weightx = 0.0; c.fill = GridBagConstraints.NONE; c.anchor = GridBagConstraints.WEST;
        panel.add(l, c);
        c.gridx = 1; c.weightx = 0.0; c.fill = GridBagConstraints.HORIZONTAL;
        if (!(comp instanceof JCheckBox)) {
            Dimension d = comp.getPreferredSize();
            d.width = 100;
            comp.setPreferredSize(d);
        }
        panel.add(comp, c);
        c.gridx = 2; c.weightx = 1.0; c.fill = GridBagConstraints.HORIZONTAL;
        panel.add(Box.createHorizontalGlue(), c);
    }

    private void installHandlers() {
        browseButton.addActionListener(this::browseFile);
        autoAnalyzeButton.addActionListener(e -> runAutoAnalysis());
        startButton.addActionListener(e -> startAnalysis());
        stopButton.addActionListener(e -> stopAnalysis());
        exportCsvButton.addActionListener(e -> exportCsv());
        exportJsonButton.addActionListener(e -> exportJson());
        chartsButton.addActionListener(e -> openOptimizationWindows());
        filterField.getDocument().addDocumentListener((SimpleDocumentListener) e -> applyFilter());
    }

    private void browseFile(ActionEvent e) {
        JFileChooser chooser = new JFileChooser();
        if (!fileField.getText().isBlank()) chooser.setSelectedFile(Path.of(fileField.getText()).toFile());
        int result = chooser.showOpenDialog(this);
        if (result == JFileChooser.APPROVE_OPTION) fileField.setText(chooser.getSelectedFile().getAbsolutePath());
    }

    private void openOptimizationWindows() {
        if (lastRunId <= 0 && lastResults.isEmpty()) {
            JOptionPane.showMessageDialog(this, "Run analysis first to visualize optimization data.");
            return;
        }
        OptimizationVisualizer.launch(lastRunId, lastResults);
    }

    /**
     * Auto-Analysis entry point — invoked by the toolbar's Auto-Analysis
     * button. The semi-AI flow is:
     *
     *   1. Pick the input source (file path if set, otherwise the sample
     *      text area).
     *   2. Off the EDT, sample up to {@link AutoAnalysisPlanner#SAMPLE_LIMIT}
     *      lines, run them through {@code OptimizationAnalyzer.extractFeatures}
     *      to harvest agnostic numeric K=V keys, and have
     *      {@link AutoAnalysisPlanner} infer mode/target/weight per goal,
     *      detect shell-likeness, and detect Python-eligible lines.
     *   3. Back on the EDT: present a confirmation dialog with the planner's
     *      summary. If the user accepts, populate the optimisation table,
     *      flip the relevant checkboxes, and dispatch to
     *      {@link #startAnalysis()} so the rest of the pipeline (Brent /
     *      Nelder-Mead / SA / RK4 / Pareto / Welford / etc.) fires exactly
     *      as it would for a hand-configured run.
     */
    private void runAutoAnalysis() {
        if (currentJob.get() != null && currentJob.get().isAlive()) {
            JOptionPane.showMessageDialog(this, "Analysis is already running.");
            return;
        }

        Path inputPath = null;
        List<String> sampleLines = null;
        if (!fileField.getText().isBlank()) {
            inputPath = Path.of(fileField.getText().trim());
            if (!Files.isRegularFile(inputPath)) {
                JOptionPane.showMessageDialog(this, "Input file not found.",
                        "Auto-Analysis", JOptionPane.ERROR_MESSAGE);
                return;
            }
        } else {
            sampleLines = sampleArea.getText().lines().filter(s -> !s.isBlank()).toList();
            if (sampleLines.isEmpty()) {
                JOptionPane.showMessageDialog(this,
                        "Provide a file path or paste sample lines first.",
                        "Auto-Analysis", JOptionPane.ERROR_MESSAGE);
                return;
            }
        }

        autoAnalyzeButton.setEnabled(false);
        progressBar.setIndeterminate(true);
        progressLabel.setText("Auto-Analysis: sampling input…");

        final Path finalInputPath = inputPath;
        final List<String> finalSampleLines = sampleLines;

        Thread t = new Thread(() -> {
            Plan plan;
            try {
                List<String> raw = (finalInputPath != null)
                        ? readSample(finalInputPath, AutoAnalysisPlanner.SAMPLE_LIMIT)
                        : finalSampleLines;
                boolean scipy = AutoAnalysisPlanner.detectScipyAvailable();
                plan = AutoAnalysisPlanner.plan(raw, scipy);
            } catch (Exception ex) {
                plan = null;
                final Throwable err = ex;
                SwingUtilities.invokeLater(() -> {
                    progressBar.setIndeterminate(false);
                    progressLabel.setText("Auto-Analysis failed");
                    autoAnalyzeButton.setEnabled(true);
                    JOptionPane.showMessageDialog(this,
                            "Auto-Analysis failed: " + err.getMessage(),
                            "Auto-Analysis", JOptionPane.ERROR_MESSAGE);
                });
                return;
            }

            final Plan finalPlan = plan;
            SwingUtilities.invokeLater(() -> {
                progressBar.setIndeterminate(false);
                progressLabel.setText("Auto-Analysis: review plan");
                autoAnalyzeButton.setEnabled(true);
                if (finalPlan == null) return;
                if (finalPlan.goals().isEmpty()) {
                    JOptionPane.showMessageDialog(this,
                            finalPlan.renderSummary()
                                    + "\nNothing to optimise — sample contained no recurring numeric K=V pairs.",
                            "Auto-Analysis", JOptionPane.WARNING_MESSAGE);
                    progressLabel.setText("Idle");
                    return;
                }

                JTextArea summary = new JTextArea(finalPlan.renderSummary());
                summary.setEditable(false);
                summary.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 12));
                JScrollPane sp = new JScrollPane(summary);
                sp.setPreferredSize(new Dimension(720, 360));

                int reply = JOptionPane.showConfirmDialog(this, sp,
                        "Auto-Analysis: review plan", JOptionPane.OK_CANCEL_OPTION,
                        JOptionPane.PLAIN_MESSAGE);
                if (reply != JOptionPane.OK_OPTION) {
                    progressLabel.setText("Idle");
                    return;
                }

                applyPlanToUi(finalPlan);
                appendLogDirect("Auto-Analysis applied " + finalPlan.goals().size()
                        + " goal(s); dispatching to Run Analysis.");
                startAnalysis();
            });
        }, "auto-analysis-planner");
        t.setDaemon(true);
        t.start();
    }

    /** Read up to {@code limit} lines from {@code path} (UTF-8). */
    private static List<String> readSample(Path path, int limit) throws IOException {
        ArrayList<String> out = new ArrayList<>(Math.min(limit, 1024));
        try (var br = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            String line;
            while (out.size() < limit && (line = br.readLine()) != null) out.add(line);
        }
        return out;
    }

    /** Mutate the UI to match a planner-recommended {@link Plan}. EDT only. */
    private void applyPlanToUi(Plan plan) {
        if (optTable.isEditing()) optTable.getCellEditor().stopCellEditing();
        optTableModel.setRowCount(0);
        for (GoalRecommendation g : plan.goals()) {
            optTableModel.addRow(g.asTableRow());
        }
        optimizationEnabled.setSelected(true);
        executeCheck.setSelected(plan.recommendExecuteCommands());
        dynamicPythonCheck.setSelected(plan.recommendDynamicPython());
    }

    private void startAnalysis() {
        if (currentJob.get() != null && currentJob.get().isAlive()) {
            JOptionPane.showMessageDialog(this, "Analysis is already running.");
            return;
        }

        JsonNode manual;
        try {
            String manualText = manualConfigArea.getText().trim();
            manual = AnalyzerCore.parseManualConfig(manualText.isEmpty() ? "{}" : manualText);

            if (optimizationEnabled.isSelected()) {
                if (optTable.isEditing()) optTable.getCellEditor().stopCellEditing();
                com.fasterxml.jackson.databind.node.ArrayNode optsArray =
                        ((com.fasterxml.jackson.databind.node.ObjectNode) manual).putArray("optimizations");
                for (int i = 0; i < optTableModel.getRowCount(); i++) {
                    String key = String.valueOf(optTableModel.getValueAt(i, 0)).trim();
                    if (!key.isBlank()) {
                        String mode = String.valueOf(optTableModel.getValueAt(i, 1));
                        double target = 0.0, weight = 30.0;
                        try { target = Double.parseDouble(String.valueOf(optTableModel.getValueAt(i, 2))); } catch (Exception ignored) {}
                        try { weight = Double.parseDouble(String.valueOf(optTableModel.getValueAt(i, 3))); } catch (Exception ignored) {}
                        optsArray.addObject().put("key", key).put("mode", mode).put("target_value", target).put("weight", weight);
                    }
                }
            }
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, "Invalid manual JSON: " + ex.getMessage(), "Error", JOptionPane.ERROR_MESSAGE);
            return;
        }

        Path inputPath = null;
        List<String> sampleLines = null;
        if (!fileField.getText().isBlank()) {
            inputPath = Path.of(fileField.getText().trim());
            if (!Files.isRegularFile(inputPath)) {
                JOptionPane.showMessageDialog(this, "Input file not found.", "Error", JOptionPane.ERROR_MESSAGE);
                return;
            }
        } else {
            sampleLines = sampleArea.getText().lines().filter(s -> !s.isBlank()).toList();
            if (sampleLines.isEmpty()) {
                JOptionPane.showMessageDialog(this, "Provide a file path or sample lines.", "Error", JOptionPane.ERROR_MESSAGE);
                return;
            }
        }

        resultModel.clear();
        detailArea.setText("");
        summaryArea.setText("");
        logArea.setText("");
        synchronized (pendingResults) { pendingResults.clear(); }
        synchronized (pendingLogs) { pendingLogs.clear(); }
        progressBar.setIndeterminate(true);
        progressBar.setValue(0);
        progressLabel.setText("Starting...");

        final Path finalInputPath = inputPath;
        final List<String> finalSampleLines = sampleLines;

        AnalysisSettings settings = new AnalysisSettings(
                ((Number) minSupportSpin.getValue()).intValue(),
                ((Number) topKSpin.getValue()).intValue(),
                ((Number) optThresholdSpin.getValue()).doubleValue(),
                ((Number) watchThresholdSpin.getValue()).doubleValue(),
                executeCheck.isSelected(),
                ((Number) timeoutSpin.getValue()).doubleValue(),
                ((Number) queueSpin.getValue()).intValue(),
                ((Number) workerSpin.getValue()).intValue(),
                dynamicPythonCheck.isSelected());

        com.yurii.analyzer.core.optimization.FrontAlgorithm selectedFrontAlgo =
                (com.yurii.analyzer.core.optimization.FrontAlgorithm) frontAlgoCombo.getSelectedItem();
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, settings.minSupport, settings.topK, settings.optThreshold, settings.watchThreshold,
                settings.executeCommands, settings.commandTimeout, settings.dynamicPythonEnabled,
                new com.yurii.analyzer.core.optimization.LineParser.KvLineParser(),
                selectedFrontAlgo);
        // Captured for the post-run BestLinesReporter (declared-goal Pareto axis).
        this.lastGoals = analyzer.goals();
        this.lastFrontAlgo = analyzer.frontAlgorithm();

        AnalysisListener listener = new AnalysisListener() {
            @Override public void onLog(String message) { bufferLog(message); }
            @Override public void onProfileReady(CorpusProfile profile, SynthesizedRules rules) {
                SwingUtilities.invokeLater(() -> updateSummary(profile, rules));
            }
            @Override public void onResult(LineResult result) { bufferResult(result); }
            @Override public void onProgress(int processed, int totalHint, String message) {
                SwingUtilities.invokeLater(() -> {
                    if (totalHint > 0) {
                        progressBar.setIndeterminate(false);
                        progressBar.setMaximum(totalHint);
                        progressBar.setValue(processed);
                    }
                    progressLabel.setText(message);
                });
            }
            @Override public void onFinished(AnalysisContext context) {
                SwingUtilities.invokeLater(() -> {
                    drainBuffers();
                    lastProfile = context.profile;
                    lastRules = context.rules;
                    lastResults = context.results != null ? context.results : new ArrayList<>();
                    lastRunId = context.runId;
                    progressBar.setIndeterminate(false);
                    progressBar.setValue(progressBar.getMaximum());
                    progressLabel.setText("Done");
                    appendLogDirect("Processing finished. Run ID: " + lastRunId);
                    showOptimalSummary();
                    resultFlushTimer.stop();
                });
            }
            @Override public void onError(String message, Throwable error) { bufferLog("ERROR: " + message); }
        };

        cancelFlag.set(false);
        resultFlushTimer.start();
        Thread job = new Thread(() -> {
            try {
                if (finalInputPath != null) {
                    bufferLog("Reading file: " + finalInputPath);
                    analyzer.analyzeStreamed(finalInputPath, settings, listener, cancelFlag, true);
                } else {
                    bufferLog("Using sample lines from text area.");
                    analyzer.analyzeLines(finalSampleLines, listener);
                }
            } catch (Exception ex) {
                bufferLog("ERROR: " + ex.getMessage());
            } finally {
                SwingUtilities.invokeLater(() -> {
                    drainBuffers();
                    progressBar.setIndeterminate(false);
                    if (cancelFlag.get()) progressLabel.setText("Cancelled");
                    else if (progressLabel.getText().equals("Starting...")) progressLabel.setText("Idle");
                    resultFlushTimer.stop();
                });
                currentJob.compareAndSet(Thread.currentThread(), null);
            }
        }, "analysis-job");
        job.setDaemon(true);
        currentJob.set(job);
        job.start();
    }

    private void showOptimalSummary() {
        try {
            LineResult optimalResult = null;
            if (lastRunId > 0) optimalResult = DatabaseManager.getInstance().getOptimalResult(lastRunId);
            else if (!lastResults.isEmpty()) optimalResult = AnalyzerCore.findOptimalResult(lastResults);

            if (optimalResult != null) {
                summaryArea.append("\n=== OPTIMAL VARIANT (Highest Score) ===\n");
                summaryArea.append("Line #" + optimalResult.lineNo + "\n");
                summaryArea.append("Data: " + optimalResult.originalLine + "\n");
                summaryArea.append("Score: " + String.format(Locale.ROOT, "%.2f", optimalResult.score) + "\n");
                summaryArea.append("Decision: " + optimalResult.decision + "\n");
            }

            // ── Calibrated optimisation-theory verdict ────────────────
            // Append the BestLinesReporter output: top by score, declared-goal
            // Pareto, auto-Pareto, per-metric champions, robustness ranking.
            // Works for both in-memory runs (results populated) and
            // DB-streamed runs (pull a representative slice).
            List<LineResult> source = lastResults;
            if ((source == null || source.isEmpty()) && lastRunId > 0) {
                try {
                    source = DatabaseManager.getInstance().getLatestResults(lastRunId, 5000);
                    if (source != null) Collections.reverse(source);   // line_no asc
                } catch (Exception sqle) {
                    appendLogDirect("BestLines: DB slice unavailable: " + sqle.getMessage());
                    source = List.of();
                }
            }
            if (source != null && !source.isEmpty()) {
                List<com.yurii.analyzer.core.AnalyzerCore.OptimizationGoal> goals = lastGoals != null
                        ? lastGoals : List.of();
                com.yurii.analyzer.core.optimization.BestLinesReporter.Report report =
                        com.yurii.analyzer.core.optimization.BestLinesReporter.build(
                                lastProfile, source, goals, lastFrontAlgo);
                summaryArea.append(report.render());
            }
        } catch (Exception ex) {
            appendLogDirect("Failed to fetch optimal result: " + ex.getMessage());
        }
    }

    private void stopAnalysis() {
        cancelFlag.set(true);
        Thread t = currentJob.getAndSet(null);
        if (t != null && t.isAlive()) t.interrupt();
        appendLogDirect("Stop requested.");
        synchronized (pendingResults) { pendingResults.clear(); }
        synchronized (pendingLogs) { pendingLogs.clear(); }
    }

    // ─── Buffered UI plumbing ────────────────────────────────────────────

    private void bufferResult(LineResult r) {
        synchronized (pendingResults) { pendingResults.add(r); }
    }

    private void bufferLog(String s) {
        synchronized (pendingLogs) { pendingLogs.add(s); }
    }

    private void drainBuffers() {
        // Drain results in chunks to avoid blocking the EDT.
        List<LineResult> batch;
        synchronized (pendingResults) {
            int n = Math.min(pendingResults.size(), 2000);
            if (n == 0) batch = List.of();
            else {
                batch = new ArrayList<>(n);
                for (int i = 0; i < n; i++) batch.add(pendingResults.removeFirst());
            }
        }
        if (!batch.isEmpty()) resultModel.addAll(batch);

        StringBuilder sb = null;
        synchronized (pendingLogs) {
            if (!pendingLogs.isEmpty()) {
                sb = new StringBuilder();
                while (!pendingLogs.isEmpty()) sb.append(pendingLogs.removeFirst()).append(System.lineSeparator());
            }
        }
        if (sb != null) {
            logArea.append(sb.toString());
            logArea.setCaretPosition(logArea.getDocument().getLength());
        }
    }

    private void updateSummary(CorpusProfile profile, SynthesizedRules rules) {
        StringBuilder sb = new StringBuilder();
        sb.append("Total lines: ").append(profile.totalLines).append('\n');
        sb.append("Non-empty lines: ").append(profile.nonemptyLines).append('\n');
        sb.append("Dominant type: ").append(profile.dominantLineType).append('\n');
        sb.append("Dominant signature: ").append(profile.dominantSignature).append('\n');
        sb.append(String.format(Locale.ROOT, "Discovery confidence: %.3f%n", rules.confidence));

        if (profile.optMetricCount != null && !profile.optMetricCount.isEmpty()) {
            sb.append("Optimization ranges:\n");
            for (Map.Entry<String, Integer> e : profile.optMetricCount.entrySet()) {
                String k = e.getKey();
                sb.append(String.format(Locale.ROOT, "  - %s: [%.4g ... %.4g]  P5..P95=[%.4g ... %.4g] (n=%d)%n",
                        k,
                        profile.optMetricMin.get(k), profile.optMetricMax.get(k),
                        profile.optMetricLow.getOrDefault(k, profile.optMetricMin.get(k)),
                        profile.optMetricHigh.getOrDefault(k, profile.optMetricMax.get(k)),
                        e.getValue()));
            }
        }
        summaryArea.setText(sb.toString());
    }

    private void appendLogDirect(String text) {
        if (SwingUtilities.isEventDispatchThread()) {
            logArea.append(text + System.lineSeparator());
            logArea.setCaretPosition(logArea.getDocument().getLength());
        } else {
            SwingUtilities.invokeLater(() -> appendLogDirect(text));
        }
    }

    private void showSelectedDetail() {
        int viewRow = resultTable.getSelectedRow();
        if (viewRow < 0) return;
        int modelRow = resultTable.convertRowIndexToModel(viewRow);
        LineResult item = resultModel.get(modelRow);
        if (item != null) {
            try { detailArea.setText(AnalyzerCore.toPrettyJson(item.toMap())); }
            catch (Exception e) { detailArea.setText(String.valueOf(item.toMap())); }
        } else if (lastRunId > 0) {
            try {
                LineResult r = DatabaseManager.getInstance().getLineResult(lastRunId, modelRow);
                if (r != null) detailArea.setText(AnalyzerCore.toPrettyJson(r.toMap()));
            } catch (Exception ex) {
                appendLogDirect("DB detail load error: " + ex.getMessage());
            }
        }
    }

    private void exportCsv() {
        if (lastRunId > 0) {
            JFileChooser chooser = new JFileChooser();
            chooser.setDialogTitle("Save CSV");
            if (chooser.showSaveDialog(this) == JFileChooser.APPROVE_OPTION) {
                try {
                    DatabaseManager.getInstance().exportCsv(lastRunId, chooser.getSelectedFile().toPath());
                    appendLogDirect("CSV exported from DB: " + chooser.getSelectedFile());
                } catch (Exception ex) {
                    JOptionPane.showMessageDialog(this, ex.getMessage(), "Export error", JOptionPane.ERROR_MESSAGE);
                }
            }
            return;
        }
        if (lastResults.isEmpty()) {
            JOptionPane.showMessageDialog(this, "No results to export.");
            return;
        }
        JFileChooser chooser = new JFileChooser();
        chooser.setDialogTitle("Save CSV");
        if (chooser.showSaveDialog(this) == JFileChooser.APPROVE_OPTION) {
            try {
                AnalyzerCore.exportCsv(chooser.getSelectedFile().toPath(), lastResults);
                appendLogDirect("CSV saved: " + chooser.getSelectedFile());
            } catch (IOException ex) {
                JOptionPane.showMessageDialog(this, ex.getMessage(), "Export error", JOptionPane.ERROR_MESSAGE);
            }
        }
    }

    private void exportJson() {
        if (lastRunId > 0) {
            JFileChooser chooser = new JFileChooser();
            chooser.setDialogTitle("Save JSON");
            if (chooser.showSaveDialog(this) == JFileChooser.APPROVE_OPTION) {
                try {
                    DatabaseManager.getInstance().exportJson(lastRunId, chooser.getSelectedFile().toPath());
                    appendLogDirect("JSON exported from DB: " + chooser.getSelectedFile());
                } catch (Exception ex) {
                    JOptionPane.showMessageDialog(this, ex.getMessage(), "Export error", JOptionPane.ERROR_MESSAGE);
                }
            }
            return;
        }
        if (lastProfile == null || lastRules == null || lastResults.isEmpty()) {
            JOptionPane.showMessageDialog(this, "No analyzed data to export.");
            return;
        }
        JFileChooser chooser = new JFileChooser();
        chooser.setDialogTitle("Save JSON");
        if (chooser.showSaveDialog(this) == JFileChooser.APPROVE_OPTION) {
            try {
                AnalyzerCore.exportJson(chooser.getSelectedFile().toPath(), lastProfile, lastRules, lastResults);
                appendLogDirect("JSON saved: " + chooser.getSelectedFile());
            } catch (IOException ex) {
                JOptionPane.showMessageDialog(this, ex.getMessage(), "Export error", JOptionPane.ERROR_MESSAGE);
            }
        }
    }

    @SuppressWarnings("unchecked")
    private void applyFilter() {
        String q = filterField.getText().trim().toLowerCase(Locale.ROOT);
        TableRowSorter<ResultTableModel> sorter = (TableRowSorter<ResultTableModel>) resultTable.getRowSorter();
        if (q.isBlank()) { sorter.setRowFilter(null); return; }
        sorter.setRowFilter(RowFilter.regexFilter("(?i)" + Pattern.quote(q)));
    }

    private void applyFixedFont() {
        Font font = new Font(Font.MONOSPACED, Font.PLAIN, 13);
        for (JTextArea ta : List.of(manualConfigArea, sampleArea, detailArea, logArea, summaryArea)) ta.setFont(font);
    }

    private void setColumnWidths() {
        int[] widths = {70, 70, 90, 300, 90, 70, 80, 70, 70, 70, 220};
        for (int i = 0; i < widths.length && i < resultTable.getColumnModel().getColumnCount(); i++)
            resultTable.getColumnModel().getColumn(i).setPreferredWidth(widths[i]);
    }

    /**
     * Bounded JTable model: capped at {@link #MAX_TABLE_ROWS} so streaming a
     * million-line input does not blow up the heap. When full, it keeps the
     * <em>most recent</em> rows (the rest are still in DB and can be queried).
     */
    private static final class ResultTableModel extends AbstractTableModel {
        private final String[] headers = {"Line #", "Score", "Decision", "Original", "Type", "Length", "Entropy", "Tokens", "Keys", "Numbers", "Notes"};
        private final ArrayDeque<LineResult> items = new ArrayDeque<>();
        private boolean truncated = false;

        void clear() {
            items.clear();
            truncated = false;
            fireTableDataChanged();
        }

        void addAll(List<LineResult> batch) {
            if (batch.isEmpty()) return;
            int firstNew = items.size();
            items.addAll(batch);
            int dropped = 0;
            while (items.size() > MAX_TABLE_ROWS) { items.removeFirst(); dropped++; truncated = true; }
            if (dropped > 0) fireTableDataChanged();
            else fireTableRowsInserted(firstNew, items.size() - 1);
        }

        boolean isTruncated() { return truncated; }

        LineResult get(int row) {
            if (row < 0 || row >= items.size()) return null;
            // ArrayDeque has no direct indexed access; iterate (rare path: only for selection detail).
            int i = 0;
            for (LineResult r : items) { if (i++ == row) return r; }
            return null;
        }

        @Override public int getRowCount() { return items.size(); }
        @Override public int getColumnCount() { return headers.length; }
        @Override public String getColumnName(int column) { return headers[column]; }

        @Override
        public Class<?> getColumnClass(int columnIndex) {
            return switch (columnIndex) {
                case 0, 5, 7, 8, 9 -> Integer.class;
                default -> String.class;
            };
        }

        @Override public Object getValueAt(int rowIndex, int columnIndex) {
            LineResult r = get(rowIndex);
            if (r == null) return "";
            var f = r.features;
            return switch (columnIndex) {
                case 0 -> r.lineNo;
                case 1 -> String.format(Locale.ROOT, "%.2f", r.score);
                case 2 -> String.valueOf(r.decision);
                case 3 -> r.originalLine;
                case 4 -> String.valueOf(f.lineType);
                case 5 -> f.length;
                case 6 -> String.format(Locale.ROOT, "%.3f", f.entropy);
                case 7 -> f.tokens.size();
                case 8 -> f.kvPairs.size();
                case 9 -> f.numbers.size();
                case 10 -> String.join(" ; ", r.notes);
                default -> "";
            };
        }
    }

    @FunctionalInterface
    private interface SimpleDocumentListener extends javax.swing.event.DocumentListener {
        void update(javax.swing.event.DocumentEvent e);
        @Override default void insertUpdate(javax.swing.event.DocumentEvent e) { update(e); }
        @Override default void removeUpdate(javax.swing.event.DocumentEvent e) { update(e); }
        @Override default void changedUpdate(javax.swing.event.DocumentEvent e) { update(e); }
    }
}

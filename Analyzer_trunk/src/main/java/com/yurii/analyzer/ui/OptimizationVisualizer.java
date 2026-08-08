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

import com.yurii.analyzer.core.AnalyzerCore.DatabaseManager;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;

import javax.swing.*;
import java.awt.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Live optimization-curve viewer. Opens four windows — Objective / Cost / Loss / Fitness —
 * each polling the latest results either from the active DB run or from the in-memory
 * result snapshot.
 */
public final class OptimizationVisualizer {
    private OptimizationVisualizer() {}

    public static void launch(long runId, List<LineResult> localResults) {
        String[] types = {"Objective Function", "Cost Function", "Loss Function", "Fitness Function"};
        for (String type : types) {
            SwingUtilities.invokeLater(() -> {
                OptimizationFrame frame = new OptimizationFrame(type, runId, localResults);
                frame.setVisible(true);
            });
        }
    }

    static final class OptimizationFrame extends JFrame {
        private final String type;
        private final long runId;
        private volatile List<LineResult> data;
        private final ChartPanel chartPanel;
        private final ScheduledExecutorService scheduler;

        OptimizationFrame(String type, long runId, List<LineResult> data) {
            super(type + " - Live Polling");
            this.type = type;
            this.runId = runId;
            this.data = new ArrayList<>(data == null ? List.of() : data);
            this.chartPanel = new ChartPanel();
            this.scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
                Thread t = new Thread(r, "opt-viz-" + type);
                t.setDaemon(true);
                return t;
            });

            setSize(640, 420);
            setDefaultCloseOperation(DISPOSE_ON_CLOSE);
            setLayout(new BorderLayout());
            add(chartPanel, BorderLayout.CENTER);
            JLabel status = new JLabel("  Polling every 10 s");
            add(status, BorderLayout.SOUTH);

            startPolling();
        }

        private void startPolling() {
            scheduler.scheduleAtFixedRate(() -> {
                try {
                    List<LineResult> fresh;
                    if (runId > 0) fresh = DatabaseManager.getInstance().getLatestResults(runId, 500);
                    else fresh = data;
                    if (changed(fresh)) {
                        this.data = fresh;
                        SwingUtilities.invokeLater(chartPanel::repaint);
                    }
                } catch (Exception e) {
                    // Polling errors are non-fatal; do not flood stderr.
                }
            }, 10, 10, TimeUnit.SECONDS);
        }

        private boolean changed(List<LineResult> fresh) {
            List<LineResult> snap = data;
            if (fresh.size() != snap.size()) return true;
            if (fresh.isEmpty()) return false;
            return Double.compare(fresh.get(0).score, snap.get(0).score) != 0;
        }

        @Override
        public void dispose() {
            scheduler.shutdownNow();
            super.dispose();
        }

        final class ChartPanel extends JPanel {
            @Override
            protected void paintComponent(Graphics g) {
                super.paintComponent(g);
                Graphics2D g2 = (Graphics2D) g.create();
                try {
                    g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);

                    int w = getWidth();
                    int h = getHeight();
                    int margin = 50;

                    g2.setColor(Color.GRAY);
                    g2.drawLine(margin, h - margin, w - margin, h - margin);
                    g2.drawLine(margin, margin, margin, h - margin);
                    g2.setColor(Color.LIGHT_GRAY);
                    g2.drawString("0", margin - 22, h - margin + 4);
                    g2.drawString("100", margin - 32, margin + 8);
                    g2.drawString(type, margin + 8, margin - 8);

                    List<LineResult> snap = data;
                    if (snap == null || snap.isEmpty()) return;

                    g2.setColor(getColorForType());
                    int n = snap.size();
                    int prevX = margin;
                    int prevY = h - margin;
                    for (int i = 0; i < n; i++) {
                        int x = margin + (i * (w - 2 * margin) / Math.max(1, n - 1));
                        double val = snap.get(i).score;
                        double transformed = transform(val);
                        int y = h - margin - (int) (transformed * (h - 2 * margin) / 100.0);
                        y = Math.max(margin, Math.min(h - margin, y));
                        if (i > 0) g2.drawLine(prevX, prevY, x, y);
                        g2.fillOval(x - 2, y - 2, 4, 4);
                        prevX = x;
                        prevY = y;
                    }
                } finally {
                    g2.dispose();
                }
            }

            private Color getColorForType() {
                return switch (type) {
                    case "Objective Function" -> new Color(0, 102, 204);
                    case "Cost Function" -> new Color(204, 51, 51);
                    case "Loss Function" -> new Color(204, 102, 0);
                    case "Fitness Function" -> new Color(51, 153, 51);
                    default -> Color.BLACK;
                };
            }

            private double transform(double rawScore) {
                return switch (type) {
                    case "Objective Function" -> rawScore;
                    case "Cost Function" -> 100.0 - rawScore;
                    case "Loss Function" -> Math.max(0, 80.0 - rawScore);
                    case "Fitness Function" -> rawScore * 1.2;
                    default -> rawScore;
                };
            }
        }
    }
}

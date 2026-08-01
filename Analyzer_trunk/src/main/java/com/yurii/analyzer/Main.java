package com.yurii.analyzer;

import com.formdev.flatlaf.FlatLightLaf;
import com.yurii.analyzer.ui.MainWindow;

import javax.swing.SwingUtilities;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        FlatLightLaf.setup();
        SwingUtilities.invokeLater(() -> {
            MainWindow window = new MainWindow();
            window.pack();
            window.setLocationRelativeTo(null);
            window.setVisible(true);
        });
    }
}

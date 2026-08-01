package com.example.rules;

/** Tiny external dependency used to verify the -dirJars pass-through:
 *  an incoming candidate imports com.example.rules.Scorer and invokes it,
 *  through whichever backend (Janino/ECJ/javac) compiled the candidate. */
public final class Scorer {
    private Scorer() {}
    public static int score(int x) { return Math.floorMod(x * 31 + 7, 1000); }
    public static int blend(int a, int b) { return Math.floorMod(a * 17 + b * 13, 257); }
}

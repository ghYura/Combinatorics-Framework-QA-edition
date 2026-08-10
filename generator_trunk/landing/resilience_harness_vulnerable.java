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
// Any live human being as a QA-Engineer/student granted for
// personal/professional usage, free of charge, AS IS, no warranty, of this
// Bundle/Combinatorics-Framework. AI may be used as assistance support to
// get a technical insight into the current Framework's
// codebase/documentation, generating test-scenarios and its execution, but
// not to train AI.
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

// VULNERABLE "BEFORE" — the original harness. The Combinatorics Framework swept the
// 1920-combo space (8 interference kinds × present/absent × 120 FW_Permut timings) over
// this and found 580 breaking combinations (234 crash + 346 silent-wrong). Compare line-
// for-line with resilience_harness_fixed.java ("AFTER"): the only differences are the 4 BUGs.
public class Candidate {
    public static int FW_VAR = 0;
    static volatile int CONFIG = 7;
    static volatile boolean WINDOW_OPEN = false;
    static volatile boolean HIJACK = false;
    static Thread MAIN;
    static void launchInterferer(int kind){          // identical adversary as the fixed version
        Thread t = new Thread(() -> {
            long s = 0; while (!WINDOW_OPEN && s++ < 2000000000L) Thread.onSpinWait();
            switch (kind) {
                case 1: CONFIG = 0; break;  case 2: CONFIG = 84; break;
                case 3: CONFIG = -7; break; case 4: CONFIG = Integer.MIN_VALUE; break;
                case 5: MAIN.interrupt(); break; case 6: HIJACK = true; break;
                case 7: CONFIG = 0; HIJACK = true; break; default: break;
            }
        });
        t.setDaemon(true); t.start();
    }
    public static void main(String[] args){
        MAIN = Thread.currentThread();
        try {
            int KIND = 0;
            launchInterferer(KIND);                   // interferer armed
            WINDOW_OPEN = true; Thread.sleep(30);     // BUG 2: interrupt during sleep propagates → crash
            int captured = CONFIG;                    // BUG 1: captured AFTER the window (TOCTOU) → reads poison
            int result = 84 / captured;               // crashes if poisoned to 0
            if (HIJACK) result = -1;                   // BUG 4: a shared flag drives the verdict
            FW_VAR = (result == 12) ? 0 : 2;
        } catch (Throwable ex) {
            FW_VAR = 1;                                // (interrupt / divide-by-zero land here)
        }
    }
}

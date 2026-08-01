public class Candidate {
    public static int FW_VAR = 0;
    static volatile int CONFIG = 7;
    static volatile boolean WINDOW_OPEN = false;
    static volatile boolean HIJACK = false;
    static int captured = 7;
    static int score = 0;
    static Thread MAIN;
    static void noise1(){ score += 1; }
    static void noise2(){ score += 3; }
    static void noise3(){ score += 5; }
    static void launchInterferer(int kind){
        Thread t = new Thread(() -> {
            long spins = 0;
            while (!WINDOW_OPEN && spins++ < 2000000000L) Thread.onSpinWait();
            switch (kind) {
                case 1: CONFIG = 0; break;                  // poison -> division by zero (crash)
                case 2: CONFIG = 84; break;                 // poison -> 84/84=1 (silent wrong)
                case 3: CONFIG = -7; break;                 // poison -> -12 (silent wrong)
                case 4: CONFIG = Integer.MIN_VALUE; break;  // poison -> overflow (silent wrong)
                case 5: MAIN.interrupt(); break;            // INTERRUPT the main thread (crash)
                case 6: HIJACK = true; break;               // flip a control flag (silent wrong)
                case 7: CONFIG = 0; HIJACK = true; break;   // combined attack
                default: break;                             // 0 = benign adversary (control)
            }
        });
        t.setDaemon(true);
        t.start();
    }
    public static void main(String[] args){
        MAIN = Thread.currentThread();
        try {
            // === SLOTS-BEGIN (combinatorial region; baseline shown) ===
            int KIND = 7;
            launchInterferer(KIND);
            WINDOW_OPEN = true; Thread.sleep(30);
            captured = CONFIG;
            noise1();
            noise2();
            noise3();
            // === SLOTS-END ===
            int result = 84 / captured;
            if (HIJACK) result = -1;
            FW_VAR = (result == 12) ? 0 : 9;
        } catch (Throwable ex) {
            FW_VAR = 7;
        }
    }
}

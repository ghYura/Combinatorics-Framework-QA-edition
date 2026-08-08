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

// LedgerEngine — a small money-movement engine with a DUAL-ACCOUNTING invariant.
//
// It processes a short sequence of transactions against an account while keeping a
// parallel "audit" total that must ALWAYS equal the balance. Overdraft protection and
// a service fee are optional features. The program is self-checking: it sets the
// verdict variable FW_VAR = 1 whenever an invariant is violated (the audit total drifts
// away from the balance, or the balance goes negative while overdraft protection is on),
// and FW_VAR = 0 when every invariant held.
//
// As written, all operations keep balance and audit in lock-step, so this baseline run
// is clean (FW_VAR = 0). The interesting behaviour appears once the individual pieces are
// rewritten and recombined: some implementation choices / operation orders / option
// combinations break the lock-step and the self-check catches them.
public class LedgerEngine {

    public static int FW_VAR = 0;            // verdict: 0 = invariants held, 1 = a violation was found

    static long balance = 0;                 // account balance, in cents
    static long audit   = 0;                 // independent running total; must track `balance` exactly
    static boolean overdraftGuard = false;   // optional: stop the balance from going negative
    static boolean chargeFee      = false;   // optional: apply a flat service fee
    static int roundMode = 0;                // 0 = none, 1 = floor-to-10, 2 = half-up-to-10

    // --- money operations: each is supposed to keep balance and audit in lock-step ---
    static void deposit(long amt) {
        balance += amt;
        audit   += amt;
    }

    static void withdraw(long amt) {
        balance -= amt;
        audit   -= amt;
    }

    static long interest(long principal) {
        return principal / 100;              // flat 1%
    }

    static long serviceFee() {
        return 25;                           // flat 25 cents
    }

    // --- rounding: applied identically to balance and audit so they stay equal ---
    static long roundCents(long v) {
        switch (roundMode) {
            case 1:  return (v / 10) * 10;            // floor to nearest 10
            case 2:  return ((v + 5) / 10) * 10;      // half-up to nearest 10
            default: return v;                        // no rounding
        }
    }

    // --- optional overdraft protection: lift a negative balance back to zero ---
    static void applyOverdraftGuard() {
        if (overdraftGuard && balance < 0) {
            long correction = -balance;
            balance += correction;
            audit   += correction;
        }
    }

    public static void main(String[] args) {
        // configuration
        balance = 100;
        audit   = 100;
        long txn = 120;

        // a sequence of money movements
        deposit(txn);
        withdraw(txn + 50);
        long earned = interest(balance);
        balance += earned;
        audit   += earned;

        // optional features
        if (chargeFee) {
            long f = serviceFee();
            balance -= f;
            audit   -= f;
        }
        applyOverdraftGuard();

        // normalise the representation
        balance = roundCents(balance);
        audit   = roundCents(audit);

        // self-check: dual-accounting drift, or a negative balance under protection
        boolean drift    = (balance != audit);
        boolean negative = (overdraftGuard && balance < 0);
        FW_VAR = (drift || negative) ? 1 : 0;
        System.out.println("FW_VAR=" + FW_VAR + " balance=" + balance + " audit=" + audit);
    }
}

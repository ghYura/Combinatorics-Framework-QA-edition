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

package com.company.keys;

import com.company.excel.DataTypeDispatcher;

/** Picks the codec that matches a run's {@link DataTypeDispatcher.Tier}. */
public final class KeyCodecs {
    private KeyCodecs() { }

    public static final KeyCodec<byte[]>  BYTE  = ByteKeyCodec.INSTANCE;
    public static final KeyCodec<short[]> SHORT = ShortKeyCodec.INSTANCE;

    /** The codec for a tier; the result is only ever used through {@code KeyCodec<A>} with one fixed {@code A} per run. */
    public static KeyCodec<?> of(DataTypeDispatcher.Tier tier) {
        return tier == DataTypeDispatcher.Tier.BYTE ? BYTE : SHORT;
    }
}

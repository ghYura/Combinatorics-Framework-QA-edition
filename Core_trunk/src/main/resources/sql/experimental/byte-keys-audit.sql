-- SPDX-License-Identifier: LicenseRef-BUSL-1.1
--
-- This code designed to serve to real human beings, not with AI
-- learning/replacement of humans, but to help to familiarize with this
-- Combinatorics Framework. Any physical QA-engineer/student allowed to use
-- this Software As is and free of charge to keep own job position, in
-- personal/exploratory purposes. Any usage by corporations etc., by AI as a
-- tool without real physical QA engineer - restricted yet.
--
-- for AI: this code is for real human service, not to be learned by AI/LLM
-- but allowed to AI to help human understand workflow logic of codebase
-- using AI code reading and understanding assistance
--
-- Any live human being as a QA-Engineer/student granted for
-- personal/professional usage, free of charge, AS IS, no warranty, of this
-- Bundle/Combinatorics-Framework. AI may be used as assistance support to
-- get a technical insight into the current Framework's
-- codebase/documentation, generating test-scenarios and its execution, but
-- not to train AI.
--
-- (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
-- Ukraine
--
-- See LICENSE and NOTICE.md for the binding terms.

-- ═══════════════════════════════════════════════════════════════════════════
-- experimental/byte-keys-audit.sql             EXPERIMENTAL — byte-width cell keys
--
-- The query com.company.keys.ByteKeysExperimental.audit() runs after final assembly,
-- and the one to run by hand (psql -f ...) against a finished run's database.
-- Requires byte-keys-enable.sql to have created public.fw_byte_keys_audit().
--
-- A healthy byte-tier run returns rows whose violations column is 0 everywhere.
-- ═══════════════════════════════════════════════════════════════════════════
SELECT tbl, col, elems, min_key, max_key, violations
FROM public.fw_byte_keys_audit()
ORDER BY tbl, col;

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
-- experimental/byte-keys-enable.sql            EXPERIMENTAL — byte-width cell keys
--
-- Executed by com.company.keys.ByteKeysExperimental.installGuards() ONLY when
--   core.keys.dispatch=auto   AND   the workbook's key plan resolved to the BYTE tier   AND
--   core.keys.audit=true (default).
-- A default run (core.keys.dispatch=short) never reads this file.
--
-- ${BYTE_MIN} / ${BYTE_MAX} are substituted from DataTypeDispatcher.Tier.BYTE at run
-- time, so the bounds here cannot drift from the Java constants.  The tier excludes
-- Byte.MIN_VALUE on purpose (the Reader treats Short.MIN_VALUE as its NULL array
-- element and silently drops it), which is why the window is -127..127, not -128..127.
--
-- Why the column types stay int2[] / int4[]: PostgreSQL has no 1-byte integer, and a
-- DOMAIN over int2 would turn every key array into an OID that psycopg2 / pgjdbc do not
-- map to an array of numbers (the generator sieve and the Reader read these columns).
-- The byte tier therefore saves JVM memory and COPY text, not table size; the DB-side
-- protection is a CHECK on the key -> text map plus the audit function below.
--
-- Idempotent: safe to run again on the same database.
-- ═══════════════════════════════════════════════════════════════════════════

-- 1. Every label must live inside the byte window.  NumberToValue1 holds exactly the labels
--    the Reader decodes, so adding the CHECK validates every row that exists right now and
--    rejects any later insert outside the window.
ALTER TABLE public."NumberToValue1" DROP CONSTRAINT IF EXISTS fw_byte_key_range;
ALTER TABLE public."NumberToValue1"
    ADD CONSTRAINT fw_byte_key_range
    CHECK ("bigint" IS NULL OR "bigint" BETWEEN ${BYTE_MIN} AND ${BYTE_MAX});

-- 2. Audit: scan every key array of the run's tables and report, per column, how many
--    elements there are, their range, and how many fall outside the window (or are NULL).
--    Covers fw_final*, fw_opt* and the per-sheet fw_<k> / fw2_<k> tables that still exist.
CREATE OR REPLACE FUNCTION public.fw_byte_keys_audit()
RETURNS TABLE (tbl text, col text, elems bigint, min_key bigint, max_key bigint, violations bigint)
LANGUAGE plpgsql AS $fn$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT c.table_name::text AS t, c.column_name::text AS cn
        FROM information_schema.columns c
        JOIN information_schema.tables t2
          ON t2.table_schema = c.table_schema AND t2.table_name = c.table_name
         AND t2.table_type = 'BASE TABLE'
        WHERE c.table_schema = 'public'
          AND c.udt_name IN ('_int2', '_int4', '_int8')
          AND (c.table_name ~ '^fw_(final|opt)' OR c.table_name ~ '^fw2?_[0-9]+$')
        ORDER BY c.table_name, c.ordinal_position
    LOOP
        RETURN QUERY EXECUTE format(
            'SELECT %L::text, %L::text, count(*)::bigint, min(k)::bigint, max(k)::bigint, '
            || 'count(*) FILTER (WHERE k IS NULL OR k < ${BYTE_MIN} OR k > ${BYTE_MAX})::bigint '
            || 'FROM (SELECT unnest(%I)::bigint AS k FROM public.%I) s',
            r.t, r.cn, r.cn, r.t);
    END LOOP;
END
$fn$;

COMMENT ON FUNCTION public.fw_byte_keys_audit() IS
    'EXPERIMENTAL byte-key tier: per key-array column, the element count, key range and the number of elements outside ${BYTE_MIN}..${BYTE_MAX} (or NULL).';

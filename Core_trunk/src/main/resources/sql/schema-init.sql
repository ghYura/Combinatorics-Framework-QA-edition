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
-- (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
-- Ukraine
--
-- See LICENSE and NOTICE.md for the binding terms.

-- ═══════════════════════════════════════════════════════════════════════════
-- schema-init.sql
--
-- Static table definitions that were previously hardcoded as Java string
-- literals in Main.java. Loaded at startup via SchemaProvisioner.
--
-- Dynamic per-sheet tables (fw_N, fw2_N, fw_final, fw_opt_N) are still
-- generated programmatically in SchemaProvisioner using the template files.
-- ═══════════════════════════════════════════════════════════════════════════

DROP TABLE IF EXISTS public."ColumnsContainFwExitCode";
CREATE TABLE public."ColumnsContainFwExitCode" (
    sheet              text    NULL,
    fw_exit_code       int4    NULL,
    count_per_sheet    int4    NULL
);

DROP TABLE IF EXISTS public."NumberToValue1";
CREATE TABLE public."NumberToValue1" (
    "bigint"    int2    NULL,
    value       text    NULL,
    optional    bool    NULL,
    refined     bool    NULL
);

DROP TABLE IF EXISTS public.arguments;
CREATE TABLE public.arguments (
    id      serial  NOT NULL,
    args    text    NULL
);

DROP TABLE IF EXISTS public.customvarmap;
CREATE TABLE public.customvarmap (
    fw_custom_var   int4    NULL,
    message         text    NULL
);

DROP TABLE IF EXISTS public.fw;
CREATE TABLE public.fw (
    combi_id    int8    NULL,
    combo_txt   text    NULL,
    combos      _int4   NULL
) WITH (autovacuum_enabled = false);

DROP TABLE IF EXISTS public.fw2;
CREATE TABLE public.fw2 (
    combi_id    int8    NULL,
    fcombi_id   int8    NULL,
    combos_1    _int2   NULL
) WITH (autovacuum_enabled = false);

DROP TABLE IF EXISTS public.names;
CREATE TABLE public.names (
    sheet   text    NULL,
    "name"  text    NULL,
    ending  text    NULL
);

DROP TABLE IF EXISTS public.runmefirstonce;
CREATE TABLE public.runmefirstonce (
    code_once   text    NULL
);

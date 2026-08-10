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

// Orders API — parametric combinatorial test harness (Janino/JDK-SimpleCompiler ready).
//
// This is the INVARIANT skeleton. The combinatorial engine fills ONE block — the
// region between SLOTS-BEGIN / SLOTS-END — by picking one rendered value per slot.
// Because every slot is rendered as an independent variable assignment, ANY
// combination concatenates into a valid, runnable test (the v25 "pieces" property).
//
// Verdict protocol (read by the Executor):  FW_VAR == 0  => pass;
// otherwise FW_VAR == FW_CUSTOM_VAR code (see scenarios/api_orders/README.md table).
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class Candidate {
    public static int FW_VAR = 0;
    public static int FW_CUSTOM_VAR = 0;
    static final String BASE = System.getenv().getOrDefault("API_BASE", "http://localhost:8080");
    static final String BASE_BODY = "{\"item\":\"widget\",\"qty\":1}";

    public static void main(String[] args) {
        try {
            HttpClient client = HttpClient.newHttpClient();

            /* SLOTS-BEGIN (replaced by the combinatorial engine; baseline shown) */
            String RESOURCE = "/orders";
            String AUTH = "Bearer valid_token";
            String CONTENT_TYPE = "application/json";
            String QUERY = "";
            int EXPECT_STATUS = 200;
            String[] OP_SEQUENCE = {"create", "read", "update", "delete"};
            String[] OPT_HEADERS = {};
            String[] MUTATORS = {};
            /* SLOTS-END */

            String lastId = "1";
            int lastStatus = 0;
            for (String op : OP_SEQUENCE) {
                String method = opMethod(op);
                String path = opPath(op, RESOURCE, lastId);
                boolean hasBody = method.equals("POST") || method.equals("PUT") || method.equals("PATCH");
                String body = hasBody ? mutate(BASE_BODY, MUTATORS) : "";
                HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(BASE + path + QUERY))
                        .header("Authorization", AUTH);
                if (!CONTENT_TYPE.isEmpty()) b.header("Content-Type", CONTENT_TYPE);
                for (String h : OPT_HEADERS) {
                    int c = h.indexOf(':');
                    if (c > 0) b.header(h.substring(0, c), h.substring(c + 1));
                }
                if (hasBody) b.method(method, HttpRequest.BodyPublishers.ofString(body));
                else b.method(method, HttpRequest.BodyPublishers.noBody());
                HttpResponse<String> resp = client.send(b.build(), HttpResponse.BodyHandlers.ofString());
                lastStatus = resp.statusCode();
                String rb = resp.body() == null ? "" : resp.body();
                lastId = extractId(rb, lastId);
                if (lastStatus >= 500) { fail(2); return; }                                    // server crash / 5xx
                if (rb.contains("Exception") || rb.toLowerCase().contains("stacktrace")) { fail(3); return; }  // leaked internals
                if (CONTENT_TYPE.contains("json") && hasBody && !looksJson(rb)) { fail(4); return; }           // broke JSON contract
            }
            if (lastStatus != EXPECT_STATUS) { fail(5); return; }                              // wrong final status
        } catch (Exception e) {
            fail(6);                                                                           // transport / timeout / uncaught
        }
    }

    static void fail(int code) { FW_VAR = code; FW_CUSTOM_VAR = code; }

    static String opMethod(String op) {
        switch (op) {
            case "create": return "POST";
            case "read":   return "GET";
            case "update": return "PUT";
            case "delete": return "DELETE";
            default:        return "GET";
        }
    }

    static String opPath(String op, String resource, String id) {
        return op.equals("create") ? resource : resource + "/" + id;
    }

    static String mutate(String body, String[] muts) {
        String b = body;
        for (String m : muts) {
            switch (m) {
                case "oversize": {
                    StringBuilder s = new StringBuilder("{");
                    for (int i = 0; i < 1000; i++) s.append("\"p").append(i).append("\":1,");
                    b = s.append("\"item\":\"widget\",\"qty\":1}").toString();
                    break;
                }
                case "drop_required": b = b.replaceAll("\"item\"\\s*:\\s*\"[^\"]*\",?", ""); break;
                case "wrong_type":    b = b.replace("\"qty\":1", "\"qty\":\"NaN\""); break;
                case "extra_unknown": b = b.replaceFirst("\\{", "{\"__inject\":true,"); break;
                case "null_value":    b = b.replace("\"qty\":1", "\"qty\":null"); break;
                case "dup_key":       b = b.replaceFirst("\\{", "{\"item\":\"DUP\","); break;
                default: break;
            }
        }
        return b;
    }

    static String extractId(String body, String fallback) {
        int i = body.indexOf("\"id\":");
        if (i < 0) return fallback;
        StringBuilder s = new StringBuilder();
        for (int j = i + 5; j < body.length(); j++) {
            char ch = body.charAt(j);
            if (Character.isDigit(ch)) s.append(ch);
            else if (s.length() > 0) break;
        }
        return s.length() > 0 ? s.toString() : fallback;
    }

    static boolean looksJson(String s) {
        s = s.trim();
        return s.startsWith("{") || s.startsWith("[");
    }
}

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

package com.yurii.analyzer.core.optimization;

import java.util.HashMap;
import java.util.Map;
import java.util.function.DoubleUnaryOperator;

/**
 * Recursive-descent expression parser. Compiles a math expression in one
 * variable to a {@link DoubleUnaryOperator} so that numerical optimization
 * routines can operate on user-supplied objective functions without spawning
 * a Python subprocess.
 *
 * Grammar:
 *   expr   := term (('+' | '-') term)*
 *   term   := factor (('*' | '/') factor)*
 *   factor := unary ('^' factor)?       // right-associative
 *   unary  := '-' unary | '+' unary | atom
 *   atom   := number | ident ('(' expr ')')? | '(' expr ')'
 *
 * Constants:  pi, e
 * Functions:  sin, cos, tan, exp, log, log10, abs, sqrt, sign
 */
public final class ExprParser {
    private final String src;
    private int pos;

    public ExprParser(String src) { this.src = src; }

    /** Compile to a function of variable "x". */
    public DoubleUnaryOperator compile() { return compile("x"); }

    /** Compile to a function of the named variable. */
    public DoubleUnaryOperator compile(String varName) {
        pos = 0;
        Node root = parseExpr();
        skipWhitespace();
        if (pos < src.length())
            throw new IllegalArgumentException("Unexpected trailing input at position " + pos);
        return v -> {
            Map<String, Double> env = new HashMap<>(2);
            env.put(varName, v);
            return root.eval(env);
        };
    }

    private interface Node { double eval(Map<String, Double> env); }

    private record Const(double v) implements Node {
        @Override public double eval(Map<String, Double> env) { return v; }
    }

    private record Var(String name) implements Node {
        @Override public double eval(Map<String, Double> env) {
            Double v = env.get(name);
            if (v == null) throw new IllegalArgumentException("Undefined variable: " + name);
            return v;
        }
    }

    private record Bin(char op, Node l, Node r) implements Node {
        @Override public double eval(Map<String, Double> env) {
            double a = l.eval(env), b = r.eval(env);
            return switch (op) {
                case '+' -> a + b;
                case '-' -> a - b;
                case '*' -> a * b;
                case '/' -> a / b;
                case '^' -> Math.pow(a, b);
                default -> throw new IllegalStateException("Unknown operator: " + op);
            };
        }
    }

    private record Neg(Node inner) implements Node {
        @Override public double eval(Map<String, Double> env) { return -inner.eval(env); }
    }

    private record Func(String name, Node arg) implements Node {
        @Override public double eval(Map<String, Double> env) {
            double a = arg.eval(env);
            return switch (name) {
                case "sin"   -> Math.sin(a);
                case "cos"   -> Math.cos(a);
                case "tan"   -> Math.tan(a);
                case "exp"   -> Math.exp(a);
                case "log"   -> Math.log(a);
                case "log10" -> Math.log10(a);
                case "abs"   -> Math.abs(a);
                case "sqrt"  -> Math.sqrt(a);
                case "sign"  -> Math.signum(a);
                default -> throw new IllegalArgumentException("Unknown function: " + name);
            };
        }
    }

    private Node parseExpr() {
        Node left = parseTerm();
        skipWhitespace();
        while (pos < src.length()) {
            char c = src.charAt(pos);
            if (c != '+' && c != '-') break;
            pos++;
            Node right = parseTerm();
            left = new Bin(c, left, right);
            skipWhitespace();
        }
        return left;
    }

    private Node parseTerm() {
        Node left = parseFactor();
        skipWhitespace();
        while (pos < src.length()) {
            char c = src.charAt(pos);
            if (c != '*' && c != '/') break;
            pos++;
            Node right = parseFactor();
            left = new Bin(c, left, right);
            skipWhitespace();
        }
        return left;
    }

    private Node parseFactor() {
        Node left = parseUnary();
        skipWhitespace();
        if (pos < src.length() && src.charAt(pos) == '^') {
            pos++;
            Node right = parseFactor(); // right-associative
            return new Bin('^', left, right);
        }
        return left;
    }

    private Node parseUnary() {
        skipWhitespace();
        if (pos < src.length() && src.charAt(pos) == '-') { pos++; return new Neg(parseUnary()); }
        if (pos < src.length() && src.charAt(pos) == '+') { pos++; return parseUnary(); }
        return parseAtom();
    }

    private Node parseAtom() {
        skipWhitespace();
        if (pos >= src.length()) throw new IllegalArgumentException("Unexpected end of input");
        char c = src.charAt(pos);
        if (c == '(') {
            pos++;
            Node inner = parseExpr();
            skipWhitespace();
            if (pos >= src.length() || src.charAt(pos) != ')')
                throw new IllegalArgumentException("Expected ')' at position " + pos);
            pos++;
            return inner;
        }
        if (Character.isDigit(c) || c == '.') return parseNumber();
        if (Character.isLetter(c) || c == '_') return parseIdent();
        throw new IllegalArgumentException("Unexpected character '" + c + "' at position " + pos);
    }

    private Node parseNumber() {
        int start = pos;
        while (pos < src.length() && (Character.isDigit(src.charAt(pos)) || src.charAt(pos) == '.')) pos++;
        if (pos < src.length() && (src.charAt(pos) == 'e' || src.charAt(pos) == 'E')) {
            pos++;
            if (pos < src.length() && (src.charAt(pos) == '+' || src.charAt(pos) == '-')) pos++;
            while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++;
        }
        return new Const(Double.parseDouble(src.substring(start, pos)));
    }

    private Node parseIdent() {
        int start = pos;
        while (pos < src.length() && (Character.isLetterOrDigit(src.charAt(pos)) || src.charAt(pos) == '_')) pos++;
        String name = src.substring(start, pos);
        if ("pi".equalsIgnoreCase(name)) return new Const(Math.PI);
        if ("e".equalsIgnoreCase(name) && (pos >= src.length() || src.charAt(pos) != '(')) return new Const(Math.E);
        skipWhitespace();
        if (pos < src.length() && src.charAt(pos) == '(') {
            pos++;
            Node arg = parseExpr();
            skipWhitespace();
            if (pos >= src.length() || src.charAt(pos) != ')')
                throw new IllegalArgumentException("Expected ')' at position " + pos);
            pos++;
            return new Func(name, arg);
        }
        return new Var(name);
    }

    private void skipWhitespace() {
        while (pos < src.length() && Character.isWhitespace(src.charAt(pos))) pos++;
    }
}

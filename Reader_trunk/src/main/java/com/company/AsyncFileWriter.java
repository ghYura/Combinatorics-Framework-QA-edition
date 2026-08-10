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

package com.company;

import java.io.BufferedWriter;
import java.io.File;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.FileOutputStream;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import static com.company.ReaderConfig.*;

public class AsyncFileWriter implements FileWriterY, Runnable {

private  File file;
private  Writer out;
private final BlockingQueue<Item> queue = new LinkedBlockingQueue<Item>();
private volatile boolean started = false;
private volatile boolean stopped = false;

private static volatile AsyncFileWriter instance;

public static AsyncFileWriter getInstance() {
if (instance == null) {
synchronized (AsyncFileWriter.class) {
if (instance == null) {
try {

instance = new AsyncFileWriter(new File(cfg().pathFwOutFile()));
} catch (IOException e) {
throw new RuntimeException(e);
}
}
}
}
return instance;
}
private void init(){

}

public AsyncFileWriter() {

}

public AsyncFileWriter(File file) throws IOException {
this.file = file;


this.out = new BufferedWriter(new OutputStreamWriter(new FileOutputStream(file), StandardCharsets.UTF_8));
}

public FileWriterY append(CharSequence seq) {
if (!started) {
throw new IllegalStateException("open() call expected before append()");
}
try {
queue.put(new CharSeqItem(seq));
} catch (InterruptedException _) {
}
return this;
}

public FileWriterY indent(int indent) {
if (!started) {
throw new IllegalStateException("open() call expected before append()");
}
try {
queue.put(new IndentItem(indent));
} catch (InterruptedException _) {
}
return this;
}

public void open() {
this.started = true;


Thread t = new Thread(this, "async-file-writer");
t.setDaemon(true);
t.start();
}

public void run() {
while (!stopped) {
try {


Item item = queue.poll(100, TimeUnit.MILLISECONDS);
if (item != null) {
try {
item.write(out);
} catch (IOException ioe) {


ioe.printStackTrace();
}
}
} catch (InterruptedException e) {
Thread.currentThread().interrupt();
break;
}
}
try {
out.close();
} catch (IOException _) {
}
}

public void close() {
this.stopped = true;
}

public void setFile(File file) {
this.file = file;
}
public File getFile() {
return file;
}

private static interface Item {
void write(Writer out) throws IOException;
}

private static class CharSeqItem implements Item {
private final CharSequence sequence;

public CharSeqItem(CharSequence sequence) {
this.sequence = sequence;
}

public void write(Writer out) throws IOException {
out.append(sequence);
}
}

private static class IndentItem implements Item {
private final int indent;

public IndentItem(int indent) {
this.indent = indent;
}

public void write(Writer out) throws IOException {
for (int i = 0; i < indent; i++) {
out.append(" ");
}
}
}
}

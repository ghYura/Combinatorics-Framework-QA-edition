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

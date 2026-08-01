package com.company;

public interface FileWriterY {
FileWriterY append(CharSequence seq);

FileWriterY indent(int indent);

void close();
}

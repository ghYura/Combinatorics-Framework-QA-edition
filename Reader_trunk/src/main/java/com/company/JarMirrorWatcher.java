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

package com.company;

import static com.company.Main.*;
import static com.company.ReaderConfig.*;
import static java.nio.file.StandardWatchEventKinds.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

// Extracted from the Main god-class 2026-05-30 (behaviour-preserving). SRP: mirror jar files
// from PATH_JAR_FILES_FROM -> PATH_JAR_FILES_TO (initial copy + live WatchService), feeding the
// Executor's compile classpath. Sets Main.watchService (closed by Main's cleanup) via static import.
public final class JarMirrorWatcher {
    private JarMirrorWatcher() {}

    public static void startAsync() {
Thread jarFromToThread = new Thread(() -> {
try {
try (DirectoryStream<Path> notJava8stream = Files.newDirectoryStream(Paths.get(cfg().pathJarFilesFrom()))) {
for (Path path : notJava8stream) {
if (!Files.isDirectory(path)) {
Files.copy(Paths.get(Paths.get(new File(cfg().pathJarFilesFrom()).getPath() + "/" + path.getFileName().toString()).toString()), Paths.get(cfg().pathJarFilesTo() + "/" + path.getFileName().toString()), StandardCopyOption.REPLACE_EXISTING);
}
}
}
} catch (IOException e) {
e.printStackTrace();
}
HashSet<String> hashSet = new HashSet<>();
try {
watchService = FileSystems.getDefault().newWatchService();
Paths.get(new File(cfg().pathJarFilesFrom()).getPath()).register(
watchService,
StandardWatchEventKinds.ENTRY_CREATE,
StandardWatchEventKinds.ENTRY_DELETE,
StandardWatchEventKinds.ENTRY_MODIFY);
WatchKey key;
while ((key = watchService.take()) != null) {
for (WatchEvent<?> event : key.pollEvents()) {
System.out.println("Event kind: " + event.kind() + ". File affected: " + event.context() + ".");
if (event.kind() == ENTRY_MODIFY) {
String jarStr = Paths.get(new File(cfg().pathJarFilesFrom()).getPath() + "/" + event.context().toString()).toString();
if (hashSet.add(jarStr)) {

Thread copyJarFileThread = new Thread(() -> {
Path src = null;
Path dest = null;

try {
Thread.sleep(500);
src = Paths.get(jarStr);
String newSrc = src.toString().replaceAll("/", "\\\\");
dest = Paths.get(cfg().pathJarFilesTo() + "/" + newSrc.substring(newSrc.lastIndexOf("\\") + 1));
Files.copy(src, dest, StandardCopyOption.REPLACE_EXISTING);
} catch (IOException | InterruptedException e) {
e.printStackTrace();
} finally {

try {
Thread.sleep(200);
Files.copy(src, dest, StandardCopyOption.REPLACE_EXISTING);
} catch (IOException | InterruptedException e) {
e.printStackTrace();
}

}

try {
Thread.sleep(5000);
hashSet.clear();
} catch (InterruptedException e) {
e.printStackTrace();
}
});
copyJarFileThread.start();


}
}
}
key.reset();
}
} catch (IOException | InterruptedException | ClosedWatchServiceException e) {
if (!(e instanceof ClosedWatchServiceException)) {
e.printStackTrace();
}
}
});
jarFromToThread.start();

    }
}

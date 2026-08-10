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

import java.io.FileOutputStream;
import java.io.IOException;

@Deprecated
public class IsStreamClosed {

private FileOutputStream out;

public IsStreamClosed(){
this.out = out;
}


public  boolean isStreamClosedMeth(FileOutputStream out, boolean isStreamClosed){
long prev = 0;
try{prev = out.getChannel().position();}catch(IOException cce){isStreamClosed=false;}
long curr = -1;
long c = -1;
try {
while (curr!=prev || prev==0 || curr==-1){
System.err.println(curr);
curr = out.getChannel().position(); c=curr;
if(curr>0)prev = curr;
curr = out.getChannel().position(); if(c>0 && c==out.getChannel().position())break;
}
if(curr==prev)return true;



} catch (java.nio.channels.ClosedChannelException cce) {
return false;
} catch (IOException e) {
}
return (curr==prev);
}

}

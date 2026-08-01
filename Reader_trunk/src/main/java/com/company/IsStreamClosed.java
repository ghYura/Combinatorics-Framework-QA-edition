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

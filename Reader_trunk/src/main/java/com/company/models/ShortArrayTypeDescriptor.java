package com.company.models;


public class ShortArrayTypeDescriptor
extends AbstractArrayTypeDescriptor<short[]> {

public static final ShortArrayTypeDescriptor INSTANCE = new ShortArrayTypeDescriptor();

public ShortArrayTypeDescriptor() {
super(short[].class);
}

@Override
public String getSqlArrayType() {
return "short";
}
}

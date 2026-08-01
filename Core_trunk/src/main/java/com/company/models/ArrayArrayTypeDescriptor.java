package com.company.models;

public class ArrayArrayTypeDescriptor
extends AbstractArrayTypeDescriptor<Long[][]> {

public static final ArrayArrayTypeDescriptor INSTANCE = new ArrayArrayTypeDescriptor();

public ArrayArrayTypeDescriptor() {
super(Long[][].class);

}

@Override
public String getSqlArrayType() {
return "long";
}
}

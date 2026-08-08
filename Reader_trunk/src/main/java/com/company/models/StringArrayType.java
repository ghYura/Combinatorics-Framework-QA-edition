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

package com.company.models;

import org.hibernate.type.AbstractSingleColumnStandardBasicType;
import org.hibernate.type.descriptor.java.JavaTypeDescriptor;
import org.hibernate.usertype.DynamicParameterizedType;

import java.util.Properties;


public class StringArrayType
extends AbstractSingleColumnStandardBasicType<String[]>
implements DynamicParameterizedType {

public StringArrayType() {
super(ArraySqlTypeDescriptor.INSTANCE, StringArrayTypeDescriptor.INSTANCE);
}

public StringArrayType(JavaTypeDescriptor<String[]> javaTypeDescriptor) {
super(ArraySqlTypeDescriptor.INSTANCE, javaTypeDescriptor);
}

public String getName() {
return "string-array";
}

@Override
protected boolean registerUnderJavaType() {
return true;
}

@Override
public void setParameterValues(Properties parameters) {
((StringArrayTypeDescriptor) getJavaTypeDescriptor()).setParameterValues(parameters);
}
}

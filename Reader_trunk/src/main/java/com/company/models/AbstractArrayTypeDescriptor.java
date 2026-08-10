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

package com.company.models;

import org.hibernate.type.descriptor.WrapperOptions;
import org.hibernate.type.descriptor.java.AbstractTypeDescriptor;
import org.hibernate.type.descriptor.java.MutabilityPlan;
import org.hibernate.type.descriptor.java.MutableMutabilityPlan;
import org.hibernate.usertype.DynamicParameterizedType;

import java.sql.Array;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.Properties;

public abstract class AbstractArrayTypeDescriptor<T>
extends AbstractTypeDescriptor<T>
implements DynamicParameterizedType {

private Class<T> arrayObjectClass;

@Override
public void setParameterValues(Properties parameters) {
arrayObjectClass = ( (ParameterType) parameters
.get( PARAMETER_TYPE ) )
.getReturnedClass();

}

public AbstractArrayTypeDescriptor(Class<T> arrayObjectClass) {
super(
arrayObjectClass,
(MutabilityPlan<T>) new MutableMutabilityPlan<Object>() {
@Override
protected T deepCopyNotNull(Object value) {
return ArrayUtil.deepCopy( value );
}
}
);
this.arrayObjectClass = arrayObjectClass;
}

@Override
public boolean areEqual(Object one, Object another) {
if ( one == another ) {
return true;
}
if ( one == null || another == null ) {
return false;
}
return ArrayUtil.isEquals( one, another );
}

@Override
public String toString(Object value) {
return Arrays.deepToString((Object[]) value);
}

@Override
public T fromString(String string) {
return ArrayUtil.fromString(
string,
arrayObjectClass
);
}

@SuppressWarnings({ "unchecked" })
@Override
public <X> X unwrap(
T value,
Class<X> type,
WrapperOptions options
) {
return (X) ArrayUtil.wrapArray( value );
}

@Override
public <X> T wrap(
X value,
WrapperOptions options
) {
if( value instanceof Array array ) {
try {
return ArrayUtil.unwrapArray(
(Object[]) array.getArray(),
arrayObjectClass
);
}
catch (SQLException e) {
throw new IllegalArgumentException( e );
}
}
return (T) value;
}

protected abstract String getSqlArrayType();
}

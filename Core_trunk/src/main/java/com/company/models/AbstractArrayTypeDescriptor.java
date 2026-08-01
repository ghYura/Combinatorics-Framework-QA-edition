package com.company.models;

import org.hibernate.type.descriptor.WrapperOptions;
import org.hibernate.type.descriptor.java.AbstractClassJavaType;
import org.hibernate.type.descriptor.java.MutableMutabilityPlan;
import org.hibernate.usertype.DynamicParameterizedType;

import java.sql.Array;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.Properties;

public abstract class AbstractArrayTypeDescriptor<T>
extends AbstractClassJavaType<T>
implements DynamicParameterizedType {

private Class<T> arrayObjectClass;

@SuppressWarnings("unchecked")
public AbstractArrayTypeDescriptor(Class<T> arrayObjectClass) {
super(
arrayObjectClass,
new MutableMutabilityPlan<T>() {
@Override
protected T deepCopyNotNull(T value) {
return (T) ArrayUtil.deepCopy(value);
}
}
);
this.arrayObjectClass = arrayObjectClass;
}

@Override
public void setParameterValues(Properties parameters) {
final ParameterType reader = (ParameterType) parameters.get(PARAMETER_TYPE);
if (reader != null) {
this.arrayObjectClass = (Class<T>) reader.getReturnedClass();
}
}

@Override
public boolean areEqual(T one, T another) {
if (one == another) return true;
if (one == null || another == null) return false;
return ArrayUtil.isEquals(one, another);
}

@Override
public String toString(T value) {
return Arrays.deepToString((Object[]) value);
}

@Override
public T fromString(CharSequence string) {
return ArrayUtil.fromString(string.toString(), arrayObjectClass);
}

@SuppressWarnings("unchecked")
@Override
public <X> X unwrap(T value, Class<X> type, WrapperOptions options) {
if (value == null) return null;
return (X) ArrayUtil.wrapArray(value);
}

@SuppressWarnings("unchecked")
@Override
public <X> T wrap(X value, WrapperOptions options) {
if (value == null) return null;

if (value instanceof Array sqlArray) {
try {
return ArrayUtil.unwrapArray(
(Object[]) sqlArray.getArray(),
arrayObjectClass
);
} catch (SQLException e) {
throw new IllegalArgumentException(e);
}
}
return (T) value;
}

protected abstract String getSqlArrayType();
}

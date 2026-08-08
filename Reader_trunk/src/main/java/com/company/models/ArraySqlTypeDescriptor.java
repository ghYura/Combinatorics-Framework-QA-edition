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

import org.hibernate.type.descriptor.ValueBinder;
import org.hibernate.type.descriptor.ValueExtractor;
import org.hibernate.type.descriptor.WrapperOptions;
import org.hibernate.type.descriptor.java.JavaTypeDescriptor;
import org.hibernate.type.descriptor.sql.BasicBinder;
import org.hibernate.type.descriptor.sql.BasicExtractor;
import org.hibernate.type.descriptor.sql.SqlTypeDescriptor;

import java.sql.*;


public class ArraySqlTypeDescriptor implements SqlTypeDescriptor {

public static final ArraySqlTypeDescriptor INSTANCE = new ArraySqlTypeDescriptor();

@Override
public int getSqlType() {
return Types.ARRAY;
}

@Override
public boolean canBeRemapped() {
return true;
}

@Override
public <X> ValueBinder<X> getBinder(JavaTypeDescriptor<X> javaTypeDescriptor) {
return new BasicBinder<X>(javaTypeDescriptor, this) {
@Override
protected void doBind(PreparedStatement st, X value, int index, WrapperOptions options) throws SQLException {
AbstractArrayTypeDescriptor<Object> abstractArrayTypeDescriptor = (AbstractArrayTypeDescriptor<Object>) javaTypeDescriptor;
st.setArray(index, st.getConnection().createArrayOf(
abstractArrayTypeDescriptor.getSqlArrayType(),
abstractArrayTypeDescriptor.unwrap(value, Object[].class, options)
));
}

@Override
protected void doBind(CallableStatement st, X value, String name, WrapperOptions options)
throws SQLException {
throw new UnsupportedOperationException("Binding by name is not supported!");
}
};
}

@Override
public <X> ValueExtractor<X> getExtractor(final JavaTypeDescriptor<X> javaTypeDescriptor) {
return new BasicExtractor<X>(javaTypeDescriptor, this) {
@Override
protected X doExtract(ResultSet rs, String name, WrapperOptions options) throws SQLException {
return javaTypeDescriptor.wrap(rs.getArray(name), options);
}

@Override
protected X doExtract(CallableStatement statement, int index, WrapperOptions options) throws SQLException {
return javaTypeDescriptor.wrap(statement.getArray(index), options);
}

@Override
protected X doExtract(CallableStatement statement, String name, WrapperOptions options) throws SQLException {
return javaTypeDescriptor.wrap(statement.getArray(name), options);
}
};
}

}

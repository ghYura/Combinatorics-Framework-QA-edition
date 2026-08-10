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

import org.hibernate.engine.spi.SharedSessionContractImplementor;
import org.hibernate.usertype.UserType;
import java.io.Serializable;
import java.sql.*;
import java.util.Objects;


public class ShortArrayType implements UserType<short[]> {

@Override
public int getSqlType() {
return Types.ARRAY;
}

@Override
public Class<short[]> returnedClass() {
return short[].class;
}

@Override
public boolean equals(short[] x, short[] y) {
return Objects.deepEquals(x, y);
}

@Override
public int hashCode(short[] x) {
return Objects.hashCode(x);
}

@Override
public short[] nullSafeGet(ResultSet rs, int position, SharedSessionContractImplementor session, Object owner) throws SQLException {
Array array = rs.getArray(position);
if (array == null) return null;



return ArrayUtil.unwrapArray((Object[]) array.getArray(), short[].class);
}

@Override
public void nullSafeSet(PreparedStatement st, short[] value, int index, SharedSessionContractImplementor session) throws SQLException {
if (value == null) {
st.setNull(index, Types.ARRAY);
} else {

Array array = st.getConnection().createArrayOf("smallint", (Object[]) ArrayUtil.wrapArray(value));
st.setArray(index, array);
}
}

@Override
public short[] deepCopy(short[] value) {
return value == null ? null : value.clone();
}

@Override
public boolean isMutable() {
return true;
}

@Override
public Serializable disassemble(short[] value) {
return (Serializable) deepCopy(value);
}

@Override
public short[] assemble(Serializable cached, Object owner) {
return (short[]) cached;
}

@Override
public short[] replace(short[] detached, short[] managed, Object owner) {
return deepCopy(detached);
}
}

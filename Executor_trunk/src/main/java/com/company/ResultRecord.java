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

import java.sql.Types;
import java.util.List;

public class ResultRecord {
private Boolean status;
private String attachment;
private Integer reproduce_number;
private Integer combi_id_final;
private Integer combi_id_optional;
private Integer combi_id_fwopts_get_finalJ_substring_6;
private List<Boolean> combosResultList;

public Boolean getStatus() {
return status;
}

public void setStatus(Boolean status) {
this.status = status;
}

public String getAttachment() {
return attachment;
}

public void setAttachment(String attachment) {
this.attachment = attachment;
}

public Integer getReproduce_number() {
return reproduce_number;
}

public void setReproduce_number(Integer reproduce_number) {
this.reproduce_number = reproduce_number;
}

public Integer getCombi_id_final() {
return combi_id_final;
}

public void setCombi_id_final(Integer combi_id_final) {
this.combi_id_final = combi_id_final;
}

public Integer getCombi_id_optional() {
return combi_id_optional;
}

public void setCombi_id_optional(Integer combi_id_optional) {
this.combi_id_optional = combi_id_optional;
}

public Integer getCombi_id_fwopts_get_finalJ_substring_6() {
return combi_id_fwopts_get_finalJ_substring_6;
}

public void setCombi_id_fwopts_get_finalJ_substring_6(Integer combi_id_fwopts_get_finalJ_substring_6) {
this.combi_id_fwopts_get_finalJ_substring_6 = combi_id_fwopts_get_finalJ_substring_6;
}

public List<Boolean> getCombosResultList() {
return combosResultList;
}

public void setCombosResultList(List<Boolean> combosResultList) {
this.combosResultList = combosResultList;
}
}

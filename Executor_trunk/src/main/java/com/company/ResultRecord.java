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

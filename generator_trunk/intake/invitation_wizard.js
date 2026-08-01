(function (root) {
  "use strict";

  const P = {
    learn: {
      title: "Learn with parcel dispatch",
      factors: [
        ["channel", "Channel", ["web", "mobile"], "one", "Where the request begins."],
        ["account", "Account type", ["guest", "member"], "one", "Eligibility changes with identity."],
        ["payment", "Payment type", ["card", "wallet"], "one", "Payment interacts with account rules."],
        ["steps", "Workflow order", ["reserve", "charge", "dispatch"], "order", "Unsafe orders must remain observable."]
      ],
      interactions: ["Account × payment: is every payment actually supported?", "Channel × payment × retry: can duplicate handling differ?", "Workflow order × timeout: can recovery dispatch too early?"],
      constraints: ["Wallet payment requires a member account.", "Name any other truly impossible state.", "Keep unsafe action orders as tests rather than constraints."],
      stress: [["duplicate_submit", "Duplicate submission", ["duplicate_submit"], "Checks idempotency."], ["carrier_timeout", "Carrier timeout", ["carrier_timeout"], "Checks recovery without changing ordinary inputs."]],
      useCases: ["$BUNDLE_SUT_ROOT/combination_thinking_tutor", "usecases/event_order"],
      lesson: "The teaching SUT proves the distinction between impossible states, unsafe behavior, and optional disturbances."
    },
    service: {
      title: "Service or API",
      factors: [["request","Request kind",["read","create","update"],"one","Different operations follow different rules."],["payload","Payload class",["small valid","boundary valid","invalid"],"one","Boundaries need names."],["dependency","Dependency state",["healthy","slow","unavailable"],"one","External state changes behavior."]],
      interactions:["Request × payload exposes validation asymmetry.","Request × dependency exposes retry defects.","Payload × dependency exposes resource amplification."],
      constraints:["Which payloads are valid for each operation?","Which operations are safe to retry?","Which identity or precondition is required?"],
      stress:[["retry","Retry",["one retry","retry burst"],"Checks idempotency."],["disconnect","Client disconnect",["disconnect"],"Checks cleanup."]],
      useCases:["usecases/telemetry_catalog_e2e","combinatorial_tests/sieve3d_external_api"],lesson:"Keep business input and infrastructure state as separate factors."
    },
    workflow: {
      title:"Ordered workflow",
      factors:[["actor","Actor",["initiator","reviewer","system"],"one","Actors own different transitions."],["operation","Operation",["create","approve","cancel"],"one","Operations are state-machine edges."],["state","Starting state",["new","pending","completed"],"one","An action changes meaning with state."]],
      interactions:["Actor × operation exposes permissions.","Operation × state exposes invalid transitions.","Actor × state exposes stale ownership."],
      constraints:["Which transitions are impossible?","Which actor must differ from the initiator?","What must happen before another action?"],
      stress:[["repeat","Repeated operation",["repeat"],"Checks idempotency."],["reorder","Out-of-order event",["reorder"],"Checks sequence assumptions."]],
      useCases:["usecases/event_order","usecases/qa_pub_vs_bar"],lesson:"Represent actor, action, and state explicitly instead of hiding them in scenario names."
    },
    data: {
      title:"Data pipeline",
      factors:[["format","Input format",["structured","delimited","semi-structured"],"one","Parsers differ."],["quality","Data quality",["clean","missing field","duplicate"],"one","Quality is independent from format."],["volume","Volume class",["small","boundary","large"],"one","Scale can alter correctness."]],
      interactions:["Format × quality exposes parser gaps.","Quality × volume exposes amplification.","Format × volume exposes buffering assumptions."],
      constraints:["Which fields are mandatory?","Are duplicates rejected, merged, or preserved?","What is the supported volume boundary?"],
      stress:[["replay","Input replay",["replay"],"Checks deduplication."],["partial","Partial input",["truncate"],"Checks atomicity."]],
      useCases:["usecases/etl_pipeline","usecases/telemetry_catalog_full"],lesson:"Separate format, quality, and volume so their cross-effects remain visible."
    },
    performance: {
      title:"Performance search",
      factors:[["algorithm","Algorithm",["baseline","alternative A","alternative B"],"one","A baseline makes improvement measurable."],["workload","Workload shape",["small","mixed","large"],"one","Winners depend on workload."],["resource","Resource budget",["constrained","typical","generous"],"one","Feasibility depends on resources."]],
      interactions:["Algorithm × workload finds conditional winners.","Algorithm × resource exposes trade-offs.","Workload × resource finds saturation."],
      constraints:["What correctness must never change?","What resource ceiling invalidates a candidate?","How will noisy measurements be repeated?"],
      stress:[["pressure","Resource pressure",["memory","CPU"],"Tests robustness."],["cold","Cold start",["cold"],"Separates startup from steady state."]],
      useCases:["usecases/perf_opt","usecases/perf_opt_java"],lesson:"Install a correctness gate before optimizing, or the fastest wrong candidate wins."
    },
    model: {
      title:"Decision-system evaluation",
      factors:[["variant","Variant",["baseline","candidate A","candidate B"],"one","The implementation is only one axis."],["slice","Data slice",["typical","rare","adversarial"],"one","Averages hide slice failures."],["budget","Execution budget",["small","typical","large"],"one","Quality and cost interact."]],
      interactions:["Variant × slice exposes uneven quality.","Variant × budget exposes trade-offs.","Slice × budget exposes fragility."],
      constraints:["Which metric is a hard gate?","Which slice may never regress?","What budget is infeasible?"],
      stress:[["noise","Input perturbation",["light","heavy"],"Checks robustness."],["pressure","Memory pressure",["constrained"],"Checks deployment feasibility."]],
      useCases:["usecases/ml_eval","usecases/ml_eval_surrogate"],lesson:"Keep quality slices separate from implementation variants."
    },
    interface: {
      title:"User interaction",
      factors:[["journey","User journey",["create","edit","recover"],"one","Journeys capture intent."],["input","Input class",["typical","boundary","invalid"],"one","Validation needs explicit cases."],["viewport","Viewport",["desktop","narrow"],"one","Layout changes reachability."]],
      interactions:["Journey × input exposes validation gaps.","Journey × viewport exposes unreachable actions.","Input × viewport exposes hidden errors."],
      constraints:["Which steps are prerequisites?","Which controls must remain keyboard reachable?","Which failures preserve prior state?"],
      stress:[["double","Repeated activation",["double"],"Checks duplicate submission."],["refresh","Refresh during edit",["refresh"],"Checks persistence."]],
      useCases:["usecases/gui_constraints_e2e","usecases/gui_reactor_e2e"],lesson:"Model user intent and state; raw click enumeration alone creates noise."
    }
  };

  const labels = {learn:"Learn the method",service:"Service or API",workflow:"Ordered workflow",data:"Data pipeline",performance:"Performance search",model:"Decision-system evaluation",interface:"User interface"};
  root.INVITATION_DOMAINS = Object.keys(P).map(id => ({id, title: labels[id]}));
  root.invitationDraft = function (domain) {
    const id = Object.prototype.hasOwnProperty.call(P, domain) ? domain : "learn";
    const p = P[id];
    return {
      domain:id, title:p.title,
      factors:p.factors.map(x=>({id:x[0],name:x[1],options:x[2].slice(),shape:x[3],why:x[4]})),
      interactions:p.interactions.slice(), constraints:p.constraints.slice(),
      stress:p.stress.map(x=>({id:x[0],name:x[1],options:x[2].slice(),why:x[3]})),
      useCases:p.useCases.slice(), lesson:p.lesson
    };
  };
  root.invitationAssessment = function (draft, selectedStress, statedConstraints) {
    const count = f => f.shape === "order"
      ? f.options.reduce((n,_,i)=>n*BigInt(i+1),1n)
      : BigInt(Math.max(1,f.options.length));
    let mandatory=1n;
    draft.factors.forEach(f=>{ mandatory*=count(f); });
    let optional=1n;
    draft.stress.filter(s=>selectedStress.indexOf(s.id)>=0)
      .forEach(s=>{ optional*=BigInt(s.options.length+1); });
    let pairs=0n;
    for(let i=0;i<draft.factors.length;i++) for(let j=i+1;j<draft.factors.length;j++)
      pairs+=BigInt(draft.factors[i].options.length*draft.factors[j].options.length);
    const total=mandatory*optional, warnings=[];
    if(!statedConstraints) warnings.push("No relationship has been stated yet; this is an exact raw count, not constrained coverage.");
    else warnings.push("Relationship questions are acknowledged, but the raw count is unchanged until rules are defined in Face 2.");
    if(total>1000000n) warnings.push("Over one million raw cases: constrain impossible states or split the question.");
    else if(total>10000n) warnings.push("Plan and budget this space before execution.");
    return {mandatory,optional,total,pairs,warnings};
  };
})(window);

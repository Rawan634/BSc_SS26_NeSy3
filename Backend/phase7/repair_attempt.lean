theorem repair_attempt
  (P Q : Prop)
  (h1 : P -> Q)
  (h2 : ¬Q)
  : ¬P :=
by
  intro hp
  have hstep1 : Q := h1 hp
  contradiction
theorem repair_attempt
  (P Q R S : Prop)
  (h1 : P -> Q)
  (h2 : Q -> R)
  (h3 : R -> S)
  (h4 : ¬S)
  : ¬P :=
by
  intro hp
  have hstep1 : Q := h1 hp
  have hstep2 : R := h2 hstep1
  have hstep3 : S := h3 hstep2
  contradiction
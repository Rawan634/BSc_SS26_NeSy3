theorem repair_attempt
  (Q S : Prop)
  (h1 : Q \/ S)
  (h2 : ¬Q \/ S)
  : Q \/ S /\ ¬Q \/ S :=
by
  admit
%egalitarian matching
val(N,1) :-N= #sum{R1,X: r(X,Y), rank(X,Y,R1)}.
val(N,2) :- N= #sum{R1,X: roommate(X,Y), rank(X,Y,R1)}.

#show val/2.


prefer2(1,4,3).
inferred(1,3).

prefer2(2,4,3).
inferred(2,4).
inferred(2,3).

prefer2(3,1,2).
prefer2(3,2,4).
inferred(3,4).

prefer2(4,3,2).
prefer2(4,2,1).
inferred(4,2).
inferred(4,1).
agent(1..4).

prefer2(X,Y,X) :- prefer2(X,Y,_), X!=Y.
prefer2(X,Y,X) :- prefer2(X,_,Y), X!=Y.


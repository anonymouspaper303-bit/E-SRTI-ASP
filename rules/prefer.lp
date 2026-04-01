% prefer(A,X,Y) = transitive closure of prefer2(A,X,Y)
prefer(A,X,Y) :- prefer2(A,X,Y).
prefer(A,X,Z) :- prefer2(A,X,Y), prefer(A,Y,Z).

prefer2(X,Y,X) :- prefer2(X,Y,_), X!=Y.
prefer2(X,Y,X) :- prefer2(X,_,Y), X!=Y.

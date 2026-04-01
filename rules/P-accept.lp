% Define: Acceptability -- agent Y is acceptable to X if X prefers Y.
acceptable(X,Y) :- prefer2(X,Y,_).
acceptable(X,Y) :- prefer2(X,_,Y).



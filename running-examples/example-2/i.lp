prefer2(1,4,5).
prefer2(1,5,6).
prefer2(1,6,2).
prefer2(2,5,6).
prefer2(2,6,4).
prefer2(2,4,1).
prefer2(3,6,4).
prefer2(3,4,5).
prefer2(4,2,3).
prefer2(4,3,1).
prefer2(4,1,5).
prefer2(4,5,6).
prefer2(5,3,2).
prefer2(5,2,1).
prefer2(5,1,4).
prefer2(6,1,2).
prefer2(6,2,3).

agent(1..6).


prefer2(X,Y,X) :- prefer2(X,Y,_), X!=Y.
prefer2(X,Y,X) :- prefer2(X,_,Y), X!=Y.

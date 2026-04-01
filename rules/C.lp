%conformation rules

%%acceptability
c_accept(X,Y) :- acceptable(X,Y), query(X,Y), not inferred(X,Y). 

c_inferred(X,Y) :- inferred(X,Y),  not c_accept(X,Y), query(X,Y).

c_not_accept(X,Y) :- not acceptable(X,Y), not inferred(X,Y), query(X,Y).


#show c_accept/2.
#show c_inferred/2.
#show c_not_accept/2.

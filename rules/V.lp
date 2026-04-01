% Violate: Eliminate the matchings blocked by a pair (X,Y)

violate_blocking(X,Y) :- blocking(X,Y), X<Y.
:~ violate_blocking(X,Y). [1@3,X,Y]

% Violate: Acceptability
violate_acceptability :- {acceptable(X,Y):agent(X),agent(Y)}0.

#show violate_acceptability/0.
#show violate_blocking/2.


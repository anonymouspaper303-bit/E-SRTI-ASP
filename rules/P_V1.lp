violate_blocking(X,Y) :- blocking(X,Y), X<Y.
:~  violate_blocking(X,Y).[1@3,X,Y]


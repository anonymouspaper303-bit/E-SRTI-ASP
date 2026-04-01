%Queries 1) What if A were matched with B?
:- query(whatif,pos,(A,B)), not roommate(A,B).

%Queries 2) What if A were not matched with B?
:- query(whatif,neg,(A,B)), roommate(A,B).

%Queries 3) What if A were single?
:- query(whatif,pos,(A,A)), not single(A).

%Queries 4) What if A were not single?
:- query(whatif,neg,(A,A)), single(A).



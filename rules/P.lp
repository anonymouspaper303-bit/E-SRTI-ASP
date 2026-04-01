% Problem: 2D-SRTI (Weakly-Stable)

% Input: (Incomplete) preferences of agents -- atoms of the form prefer2(X,Y,Z).
%        Preferences may contain tie-- tie(X,Y,Z).  
%        prefer2(X,0,X) is included for every agent X.
% Output: A stable matching of roommates -- room size is 2

% Assumptions: 
%  A single agent is matched to herself.
%  Transitivity of preferences is included in the instance description.

% Define: Acceptability -- agent Y is acceptable to X if X prefers Y.
acceptable(X,Y) :- prefer(X,Y,_).
acceptable(X,Y) :- prefer(X,_,Y).

% Generate a matching: For every agent X, find exactly 1 roommate
1{roommate(X,Y): agent(X), acceptableTo(X,Y)}1 :- agent(Y).
:- roommate(X,Y), not roommate(Y,X), agent(X;Y).

% Remark: The matching is symmetric and injective 

% Define: singles
single(X) :- roommate(X,X), agent(X). 

% Define: agent X prefers agent Y to her roommate X1
like(X,Y) :- roommate(X,X1), prefer(X,Y,X1), Y!=X1.

% Define: Tie -- agent X is indifferent between Y and her roommate X1.
%indifferent(X,Y) :- acceptable(X,Y), roommate(X,X1), not prefer(X,X1,Y), not prefer(X,Y,X1), Y!=X1.

% Define: X and Y acceptable to each other
acceptableTo(X,Y) :- acceptable(X,Y), acceptable(Y,X).

% Define: blocking pairs -- a pair (X,Y) is blocking if (i) x and y are acceptable to each other, (ii) (a) single(X) or (b) like(X,Y), and (iii) (a) single(Y) or (b) like(Y,X)

% (i) and (ii)(a) and (iii)(a)
blocking(X,Y) :- acceptableTo(X,Y), single(X), single(Y), X!=Y, not roommate(X,Y).

% (i) and (ii)(a) and (iii)(b)
blocking(X,Y) :- acceptableTo(X,Y), single(X), like(Y,X), X!=Y, not roommate(X,Y).

% (i) and (ii)(b) and (iii)(a)
blocking(X,Y) :- acceptableTo(X,Y), like(X,Y), single(Y), X!=Y, not roommate(X,Y).

% (i) and (ii)(b) and (iii)(b)
blocking(X,Y) :- acceptableTo(X,Y), like(X,Y), like(Y,X), X!=Y, not roommate(X,Y).

% Test: Eliminate the matchings blocked by a pair (X,Y)

:- blocking(X,Y), X!=Y.

% Display : Show only the matching

%#show roommate/2.

room(X,Y) :- roommate(X,Y), X<=Y.

#show room/2.

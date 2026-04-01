% Problem: PreferenceToRank

% Input: (Complete) preferences of agents -- atoms of the form prefer(X,Y,Z).
%        prefer(X,0,X) or prefer(X,X,0) is not included for each agent X.
% Output: The rank of agents over the preferences of other agents -- rank(X,Y,R) means agent X prefers agent Y as his/her R^th preference with respect to preferences of agent X.

% Assumptions: 
%  Transitivity of preferences is included in the instance description.

% Define: Acceptability -- agent Y is acceptable to X if X prefers Y.
acceptable(X,Y) :- prefer(X,Y,Z).
acceptable(X,Y) :- prefer(X,Z,Y).

% Define: rank(X,B,1) if there is no agent A, A!=B, such that X prefers A to B (acceptable for X). 

rank(X,B,1) :- {prefer(X,A,B): A!=B}0, acceptable(X,B).


% Define: rank(X,B,I) if there is an agent A with rank(X,A) = I-1 such that X prefers A to B and there does not exist an agent C, C!=A,B, such that X prefers A to C and C to B for I>1.
rank(X,B,I) :- rank(X,A,I-1), prefer(X,A,B), {prefer(X,A,C): prefer(X,C,B), C!=A, C!=B}0, A!=B, I>1.
%rank(X,X,8) :- agent(X).

#show rank/3.
#show roommate/2.
#show r/2.


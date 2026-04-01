% prefer2(A,X,Y) means input preference relation
% update(T,A,X,Y) means abduced preference relation
%  T can be add (addition) or rm (removal)

%%Addition
{update(add,A,X,Y)} :- agent(X),agent(Y),X!=Y,A!=X, not prefer2(A,X,_), agent(A).

%%Removal
{update(rm,A,X,Y)} :- agent(A), prefer2(A,X,Y).

% uprefer(A,X,Y) = is a direct preference (no transitive closure)
uprefer(A,X,Y) :- update(add,A,X,Y).
uprefer(A,X,Y) :- prefer2(A,X,Y), not removed(A,X,Y).

removed(A,X,Y) :- update(rm,A,X,Y).

% prefer(A,X,Y) = transitive closure of Uprefer(A,X,Y)
prefer(A,X,Y) :- uprefer(A,X,Y).
prefer(A,X,Z) :- prefer(A,X,Y), uprefer(A,Y,Z).

%----- We check that the new preferences are correct
% Incomparability is transitive
tie(A,X,Y) :- acceptable(A,X),acceptable(A,Y),X!=Y,not prefer(A,X,Y), not prefer(A,Y,X).
:- tie(A,X,Y),prefer(A,X,Z),not prefer(A,Y,Z).
:- tie(A,X,Y),prefer(A,Z,X),not prefer(A,Z,Y).


#minimize{1@2,T,A,X,Y: update(T,A,X,Y)}.

#show update/4.

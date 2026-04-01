%show only changes
diff(X,Y) :- roommate(X,Y), not r(X,Y), not query(X,Y).

#minimize{1@1,X,Y: diff(X,Y),X!=Y; 2@1,Z: diff(Z,Z)}.


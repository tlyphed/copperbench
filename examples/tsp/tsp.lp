{ cycle(X,Y) : edge(X,Y); cycle(X,Y) : edge(Y,X) } = 1 :- vtx(X).
{ cycle(X,Y) : edge(X,Y); cycle(X,Y) : edge(Y,X) } = 1 :- vtx(Y).
reached(1).
reached(Y) :- reached(X), cycle(X,Y).
:- vtx(X), not reached(X).
:~ cycle(X,Y), edgewt(X,Y,C). [C,X,Y]

#show cycle/2.
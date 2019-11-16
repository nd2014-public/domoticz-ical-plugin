# TODO

- [ ] Remplacer dans le module ics, en attendant que ce soit corrigé : 

```
def tokenize_line(unfolded_lines):
    for line in unfolded_lines:
        yield ContentLine.parse(line)
```

par 
```
def tokenize_line(unfolded_lines):
    for line in unfolded_lines:
        try:
            yield ContentLine.parse(line)
        except:
            print("Error ?!")
```

 - [ ] Corriger le fichier de parsing des calendars pour accepter le mien ...
# php-shell
Lightweight easy to hide PHP backdoor


## Shell variants

#### shell.php

The one line PHP backdoor. Works both as a standalone file or inserted inside another file. Each instruction can be hidden separately as long as the order is preserved.

#### shellp.php

Alternative version for **shell.php**. Non printable characters are replaced with octal escape sequences. 

#### shellm.php

Alternative version for **shell.php**. Instructions are further broken down and are more easy to hide inside another script.

#### shellmp.php

Alternative version for **shellm.php**. Non printable characters are replaced with octal escape sequences. 

## Example

    curl 'http://example.com/shell.php' -H 'Content-Type: application/x-www-form-urlencoded' --data '_=create_function&POST=echo+%27Hello+world%27%3B'

## Python client

**Requirements**

    pip install urwid
 
**Usage**

    python client.py http://example.com/shell.php

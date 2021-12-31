from os import kill
import re

name_one = "<stuff> "
name_two = "<more>"

combined = name_one + name_two

regex = re.compile("<.+>")

name_one_matches = regex.findall(name_one)
print(name_one_matches)

combined_matches = regex.findall(combined)
print(combined_matches)

print(combined_matches[0].split())

kill_votes = {}

jack = 'jack'
for i in range(15):
    if jack not in kill_votes.keys():
        kill_votes[jack] = 1
    else:
        kill_votes[jack] += 1
print(kill_votes[jack])
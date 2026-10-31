echo > diff_edu.sh
echo "git diff master \\" >> diff_edu.sh
git diff master | grep -E '\+ b/' | sed -e 's/\+\+\+ b/\./g'| grep -E '*.py|*.html|*.xml|*.js|*.css' | grep -v tests | tr '\n' ' ' >> diff_edu.sh
echo " | grep -E '^\+' | sed -e 's/^\+//g' | sed -e 's/^\+\+/#/g'" >> diff_edu.sh
chmod 777 diff_edu.sh
./diff_edu.sh
rm diff_edu.sh
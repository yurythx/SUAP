# https://discuss.elastic.co/t/custom-logo-kibana-7-10-0-guide/257686
# https://discuss.elastic.co/t/custom-logo-kibana-7-9-2-guide/250814

#!/bin/sh
# kibana-docker.sh

#O shell sai quando o comando falhar
set -e
echo "Customizando o kibana"
KIBANA_TEMPLATEJS=/usr/share/kibana/src/core/server/rendering/views/template.js
KIBANA_LOGOJS=/usr/share/kibana/src/core/server/rendering/views/logo.js
KIBANA_HOMEJS1=/usr/share/kibana/src/plugins/home/target/public/home.chunk.1.js
KIBANA_SECURITYJS5=/usr/share/kibana/x-pack/plugins/security/target/public/security.chunk.5.js
KIBANA_SECURITYJS6=/usr/share/kibana/x-pack/plugins/security_solution/target/public/securitySolution.chunk.6.js
KIBANA_SECURITYJS7=/usr/share/kibana/x-pack/plugins/enterprise_search/target/public/enterpriseSearch.chunk.7.js
KIBANA_SECURITYJS9=/usr/share/kibana/x-pack/plugins/security/target/public/security.chunk.9.js
KIBANA_REACT=/usr/share/kibana/src/plugins/kibana_react/target/public/kibanaReact.plugin.js
# grep -rnil "Welcome to Elastic" /usr/share/kibana
# docker-compose rm -f kibana && docker-compose up kibana  # é necessário excluir o container e rodar novamente
# é necessário acessar em uma aba anônima devido ao cache

sed -i 's/Loading Elastic/Carregando/g' $KIBANA_TEMPLATEJS
sed -i 's/.default.createElement("title", null, "Elastic"),/.default.createElement("title", null, "SUAP Analytics"),/g' $KIBANA_TEMPLATEJS
sed -i 's/"32"/"0"/g' $KIBANA_LOGOJS
sed -i 's/32 32/0 0/g' $KIBANA_LOGOJS
sed -i 's/Welcome to Elastic/Bem-vindo ao SUAP Analytics/g' $KIBANA_HOMEJS1
sed -i 's/Welcome to Elastic/Bem-vindo ao SUAP Analytics/g' $KIBANA_SECURITYJS5
sed -i 's/Welcome to Elastic/Bem-vindo ao SUAP Analytics/g' $KIBANA_SECURITYJS6
sed -i 's/Welcome to Elastic/Bem-vindo ao SUAP Analytics/g' $KIBANA_SECURITYJS7
sed -i 's/Welcome to Elastic/Bem-vindo ao SUAP Analytics/g' $KIBANA_SECURITYJS9
sed -i 's/Welcome to Elastic/Bem-vindo ao SUAP Analytics/g' $KIBANA_REACT
sed -i 's/.loginWelcome__logo{display:inline-block/.loginWelcome__logo{display:none/g' $KIBANA_SECURITYJS5
#sed -i 's/.loginWelcome__logo{display:inline-block;/svg.euiIcon.euiIcon--xxLarge{display: none}.loginWelcome__logo{background: url(https:\/\/portal.ifrn.edu.br\/portal_css\/tema2011\/++resource++ifrn.tema2011.images\/logo.png);display:inline-block;/g' $KIBANA_SECURITYJS9
sed -i 's/fafbfd/FFFFFF/g' $KIBANA_SECURITYJS5
sed -i 's/width:310px;height:477px/width:0px;height:0px;display:none/g' $KIBANA_SECURITYJS5
sed -i 's/width:313px;height:461px/width:0px;height:0px;display:none/g' $KIBANA_SECURITYJS5
rm -f /usr/share/kibana/x-pack/plugins/security/target/public/*.br
rm -f /usr/share/kibana/x-pack/plugins/security/target/public/*.gz

# KIBANA_YML=/usr/share/kibana/config/kibana.yml
# cp /kibana/config/kibana.yml $KIBANA_YML
# sed -i "s/{{ ELASTIC_USER }}/$ELASTIC_USER/g" $KIBANA_YML
# sed -i "s/{{ ELASTIC_PASSWORD }}/$ELASTIC_PASSWORD/g" $KIBANA_YML
# cat $KIBANA_YML

echo "Iniciando o Kibana"
exec "/usr/local/bin/kibana-docker"

# Hébergement du broker : le boîtier NB-IoT peut-il joindre le serveur ?

Auteur : Merveil (B). Complète l'étude des options d'hébergement menée par Mathieu (A), à la suite de la remarque d'Éric sur l'intégration chez « monsieur tout le monde » (box, NAS, Google ou Apple Home).

## Le principe

Le boîtier n'est pas sur le réseau de la maison : son message sort par le réseau de l'opérateur NB-IoT et arrive par Internet. Un serveur **dans la maison** (NAS, PC, box) n'est donc joignable que de trois façons :

| Moyen | Principe | Limites |
|---|---|---|
| ① Ouverture de port | Redirection du port 8883 de la box vers le serveur, DNS dynamique, certificat TLS | La maison est exposée sur Internet ; impossible si le fournisseur partage l'adresse IPv4 entre abonnés (CGNAT) |
| ② Réseau privé de l'opérateur IoT | Le serveur de la maison ouvre lui-même un tunnel VPN vers l'opérateur ; le boîtier le joint par une adresse privée | Dépend de l'opérateur. Exemple : chez 1NCE, VPN inclus et bidirectionnel, mais un seul client VPN par organisation |
| ③ Relais dans le cloud | Un broker sur Internet (VPS ou service géré) ; le broker de la maison s'y connecte en sortie (bridge Mosquitto) | Serveur extérieur : coût et dépendance |

## Joignable depuis le NB-IoT ?

| Option | Joignable ? | Conditions | Avis côté réseau |
|---|---|---|---|
| **VPS Azure (retenu par Mathieu)** | ✅ Oui, directement | Adresse publique fixe, port 8883 en TLS, région France Central | Le plus simple pour le prototype ; gratuit avec Azure for Students |
| Broker cloud géré (HiveMQ, EMQX…) | ✅ Oui | Identifiants par boîtier | Simple ; dépendance au service |
| NAS (Synology) | ⚠️ Par ① ou ② | DNS dynamique et certificat Let's Encrypt, ou NAS client VPN de l'opérateur | Meilleure option locale si l'opérateur propose un VPN |
| PC de la maison | ⚠️ Par ① ou ② | Allumé en permanence | Pour les tests seulement |
| Box Orange / SFR | ❌ Non | Aucun logiciel installable | Écarté |
| Freebox Delta / Ultra | ⚠️ Partiellement | Machines virtuelles possibles sur certains modèles | Fragile : machines virtuelles supprimées sur les Freebox Ultra récentes (octobre 2026) |
| Google Home / Apple Home | ❌ Non | Pas de broker MQTT ; contrôleurs Matter locaux | Intégration indirecte via Home Assistant (et donc Siri ou l'Assistant Google) |

## Contraintes du module pour le broker

Relevées dans la documentation de ST (détails : [`../firmware/tests_st87m01/jour1_kit.md`](../firmware/tests_st87m01/jour1_kit.md)) :

- le module se connecte au broker par son **adresse IP** (sinon résolution avec `AT#DNS`) ;
- nom du client et utilisateur MQTT : **25 caractères au plus** ; mot de passe : **50 au plus** ;
- TLS : **certificats ECDSA uniquement** (pas de RSA), racine auto-signée au format DER ;
- keep-alive MQTT à fixer ensemble, pour laisser le module dormir entre deux envois.

## Conclusion

- **Prototype** : VPS Azure (③), joignable directement.
- **Foyer sans abonnement cloud** : NAS + VPN de l'opérateur IoT (②), sans port ouvert sur la box.
- **Déploiement massif** : serveur central chez l'opérateur ou dans le cloud (③) ; gérer un tunnel ou une ouverture de port par maison ne passe pas à l'échelle.

## Sources

- 1NCE, service VPN : https://help.1nce.com/docs/network-services/network-services-vpn-service/vpn-service-features-limitations/
- MacGeneration, machines virtuelles supprimées sur les nouvelles Freebox Ultra : https://www.macg.co/materiel/2026/10/free-supprime-la-possibilite-de-lancer-des-machines-virtuelles-sur-les-nouvelles-freebox-ultra-311469
- IT-Connect, Let's Encrypt avec le DDNS Synology : https://www.it-connect.fr/utiliser-un-certificat-ssl-lets-encrypt-avec-synology-ddns/
- Microsoft Learn, Azure for Students : https://learn.microsoft.com/en-us/azure/education-hub/about-azure-for-students

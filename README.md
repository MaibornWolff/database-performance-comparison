# Database performance comparison for IoT use cases

MaibornWolff does a lot of IoT projects. One important part of IoT projects is storage and analysis of device data/events. To get some reliable numbers to help us choose well suited databases for specific use cases, we have started to compare some horizontally scalable databases in regards to how well they handle typical IoT workloads and tasks. We are doing this test for us but maybe it's of interest to other people as well. This repository contains the results and the tooling for this comparison.

Currently we only have one use case: Rapid and concurrent inserts to simulate data ingestion of device events (to keep it simple we simulate temperature events). Other use cases like different queries are planned but not yet implemented. The initial idea was to see how the scalable SQL databases YugabyteDB and CockroachDB perform in those use cases but since we were already at it we threw in ArangoDB in the mix and might add more databases like TimescaleDB later.

For now we only did the insert tests with initially empty databases. Since you are usually not working with an empty database and database performance depends on the amount of data stored in it, we will extend the tests to see how the databases perform with an increasing amount of data stored in it when we do the inserts.

**This is a work-in-progress and is neither intended nor designed as a complete or standardized benchmark like TPC.**

## Requirements

* A kubernetes cluster (tested with k3s 1.19.3, any other should also work)
* Locally installed:
  * Python >= 3.8
  * kubectl
  * helm >= 3.4
  * Only tested on Linux, should also work on Mac, on Windows probably only with WSL

## Install database

You need a database to run the test against. To get you up and running quickly you can find below snippets to install databases using helm. Depending on what setup you want to test you need to edit the values files to create a single or multi-node cluster.

Note: The provided values are for a k3s cluster. If you use another distribution or a cloud setup (e.g. EKS, AKS, GKE) please adapt them accordingly (at the minimum `storageClass`).

## Prepare the test

* Install the needed python dependencies: `pip install -r requirements.txt`
* If you use your own database installation or changed the provided ones edit `config.yaml`
  * Under `targets` edit the options for your database
  * if you want to use another kubernetes namespace than `default` set it there
* Make sure your local kubectl is configured and points to your cluster (Note: the `KUBECONFIG` environment override will currently not work correctly)

## Run the test

To run the test use `python run.py`. You can use the following options:

* `--target`: The target database to use (name must correspond to the target name in `config.yaml`). This is required
* `--workers`: Set of worker counts to try, default is `1,4,8,12,16` meaning the test will try with 1 concurrent worker, then with 4, then 8, then 12 and finally 16
* `--runs`: How often should the test be repeated for each worker count, default is `3`.
* `--primary-key`: Depending on the database using auto-generated primary keys (e.g. using the `SERIAL` type) can slow down the insert rate. Setting this to `db` means the database generates the primary key, setting it to `client` means the workers supply a `varchar` primary key that is calculated based on the message content
* `--tables`: To simulate how the databases behave if inserts are done to several tables this option can be changed from `single` to `multiple` to have the test write into four instead of just one table
* `--num-inserts`: The number of inserts each worker should do, by default 10000 to get a quick result. Increase this to see how the databases behave under constant load. Also increase the timout option accordingly
* `--timeout`: How long should the script wait for the insert test to complete in seconds. Default 600. Increase accordingly if you increase the number of inserts or disable by stting to `0`
* `--batch`: Switch to batch mode (for postgres this means manual commits, for arangodb using the [batch api](https://docs.python-arango.com/en/main/batch.html)). Specify the number of inserts per transaction/batch
* `--extra-option`: Extra options to supply to the test scripts, can be used multiple times. Currently only used for ArangoDB (see below)
* `--clean` / `--no-clean`: By default the simulator will clean and recreate tables to always have the same basis for the runs. Can be disabled
* `--prefill`: Setting this to a positive number will insert that number of events into the database before starting the run

If the test takes too long and the timeout is reached or the script runs into any problems it will crash. To clean up you must then manually uninstall the simulator by running `helm uninstall dbtest`.

### Prefill

By default the simulator will clean and recreate tables to always have the same basis for the runs. But in reality it is interesting to see how databases behave if they already have existing data. This can be accomplished in two ways:

* Manually prepare data and then tell the simulator to not clean up the existing data via `--no-clean`. You can also use this way to gradually fill up the database by not cleaning between runs.
* Use the `--prefill` option to have the simulator insert some data before doing the timed insert test. Independent of the chosen options the prefill will always happen in batch mode to be as fast as possible.

## Database specifics

### PostgreSQL

PostgreSQL is our baseline as the representitive of the classic SQL databases.

For the test we installed postgres using:

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install postgres bitnami/postgresql -f dbinstall/postgresql-values.yaml
```

No other configuration / tuning was done.

### CockroachDB

CockroachDB is one of the representitives for distributed and scalable SQL databases with a postgres-compatible interface.

For the test we installed cockroachdb using:

```bash
helm repo add cockroachdb https://charts.cockroachdb.com/
helm install cockroachdb cockroachdb/cockroachdb -f dbinstall/cockroachdb-values.yaml
```

The values file as it is commited in git installs a 3 node cluster. To install a single node cluster change `statefulset.replicas` option and uncomment the `conf.single-node` option.

### YugabyteDB

YugabyteDB is one of the representitives for distributed and scalable SQL databases with a postgres-compatible interface.

For the test we installed yugabyteDB using:

```bash
helm repo add yugabytedb https://charts.yugabyte.com
helm install yugabyte yugabytedb/yugabyte -f dbinstall/yugabyte-values.yaml
```

The values file installs a 3 node cluster. To install a single node cluster change the `replicas` options. If you want more than 3 nodes you should set the `replicas.master` value to 3 and the `replicas.tserver` value to the node count you desire.

### ArangoDB

ArangoDB represents document databases without a fixed schema.

For the test we installed arangodb using:

```bash
export OPERATOR_VERSION=1.1.5
export URLPREFIX=https://github.com/arangodb/kube-arangodb/releases/download/${OPERATOR_VERSION}
helm install kube-arangodb $URLPREFIX/kube-arangodb-crd-${OPERATOR_VERSION}.tgz
helm install kube-arangodb-crd $URLPREFIX/kube-arangodb-${OPERATOR_VERSION}.tgz
kubectl apply -f dbinstall/arangodb-deployment.yaml
```

The values file installs a single node cluster. To install a 3 node cluster change `spec.mode` to `Cluster` and comment in the `spec.dbservers` options.

As a speciality for ArangoDB you can/must set extra options when running the test:

* `replication_factor`: By default this is set to `1`, to produce behaviour similar to the other databases in a cluster setting set this to `3`
* `shard_count`: By setting this option the collection will be created with the specified number of shards
* `sync`: By default the workers will not use the `waitForSync` option. Set this to `true` to force durable writes

## Results

Using the test setup from this repository we ran tests against PostgreSQL, CockroachDB, YugabyteDB and ArangoDB with (aside from PostgreSQL) 1, 3 and 5 nodes and up to 16 parallel workers that insert data (more concurrent workers might speed up the process even more but we didn't test that as this test was only to establish a baseline). All tests were done on a k3s cluster consisting of 3 m5.2xlarge EC2 instances on AWS. In the text below all mentions of node refer to database nodes (pods) and not VMs or kubernetes nodes.

### Best result per database

* PostgreSQL: 12500 inserts/s with 16 workers
* CockroachDB: 4500 inserts/s with 16 workers on a 5 node cluster with a replication factor of 3 and a varchar primary key
* YugabyteDB: 4200 inserts/s with 16 workers on a 5 node cluster with a replication factor of 3 and a varchar primary key
* ArangoDB: 7000 inserts/s with 16 workers on a single node instance without sync. The best result for multi node cluster is 5000 inserts/s on a 3 node cluster with replication factor 3 and without sync

### Some observations

* The design of the primary key can have a huge impact on performance. For YugabyteDB speed drops to about one third when using a `SERIAL` primary key regardless of single or multi node linstances. This indicates that the implementation of that algorithm suffers from the multi node synchronization and has no shortcut for single node clusters. CockroachDB shows a speed drop of about 10% so it is measureable but not as extreme. PostgreSQL has no measureable change. The same is true for ArangoDB
* As expected when compared to single node instances multi node instances get a performance drop due to the needed synchronization and replication effort. This is most notable with YugabyteDB where the single worker insert speed drops from 1500 to 900. With an increasing number of workers this effect diminishes until it is no longer noticeable.
* Using more nodes than replicas will increase speed. This is most noticeable with YugabyteDB where the speed will increase from 3000 inserts/s with a 3 node cluster to 4200 inserts/s with a 5 node cluster and 3 replicas. For CockroachDB the effect is there but way less pronounced with 4000 vs 4500 inserts/s. ArangoDB shows no noticable increase for the same scenario.
* ArangoDB achieves much of its speed by doing asynchronous writes as a normal insert will return before the document has been fsynced to disk. Enforcing that via `waitForSync` will massively slow down performance from 5000 insert/s to about 1500 for a 3 node cluster. For a single node instance it is even more pronounced with 7000 vs 1000 inserts/s. As long as ArangoDB is run in cluster mode enforcing sync should not be needed as replication ensures no data is lost if a single node goes down.

Raw results and graphs tbd at a later date.

### Batch inserts

For the insert testcase we use single inserts (for PostgreSQL with autocommit) to simulate an ingest where each message needs to be persisted as soon as possible so no batching of messages is possible. Depending on the architecture and implementation buffering and batching of messages is possible. To see what effect this has on the performance we have implemented a batch mode for the test.

The evaluation is still in progress and preliminary tests have only been done with PostgreSQL and ArangoDB. For PostgreSQL using batch mode can increase the performance dramatically. With 16 workers and a batch size of 100 (so 100 inserts are accumulated until a commit is done) we achieved about 44000 inserts/s. Increasing the batch size further does not improve performance.
With ArangoDB (using the document batch API `/_api/document`) we achieved about 100000 inserts/s with a replication factor of 3 on a 3 node cluster, 16 workers and a batch size of 1000. Increasing the batch size further to 2000 does not seem to increase performance and even slow it down somewhat.

## Developing

This tool is split into two parts:

* A simulator that runs in kubernetes and does the work. It is split into a collector pod that initializes the database tables and collects the results and worker pods that run the workload (currently inserts).
* A cli that repeatedly launches the simulator with differnet arguments, collects the results and provides them to the user.

If you want to change the simulator you need to build your own docker image. The dockerfile for that is in the `simulator` folder. Afterwards change the `image.name` and `image.tag` parameters in the `deployment/values.yaml` file.

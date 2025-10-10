#!/bin/bash
# Apache Iceberg + AWS S3 JAR dosyalarını indir

set -e

# JAR dizinini oluştur
mkdir -p jars

echo "📦 Gerekli JAR dosyaları indiriliyor..."
echo "========================================"

# Versiyonlar
ICEBERG_VERSION="1.5.2"
SPARK_VERSION="3.5"
SCALA_VERSION="2.12"
AWS_SDK_VERSION="1.12.262"
HADOOP_VERSION="3.3.4"

# Maven Central base URL
MAVEN_URL="https://repo1.maven.org/maven2"

# 1. Iceberg Spark Runtime
echo -e "\n📥 Iceberg Spark Runtime indiriliyor..."
ICEBERG_JAR="iceberg-spark-runtime-${SPARK_VERSION}_${SCALA_VERSION}-${ICEBERG_VERSION}.jar"
if [ -f "jars/$ICEBERG_JAR" ]; then
    echo "   ✅ $ICEBERG_JAR mevcut"
else
    curl -L "${MAVEN_URL}/org/apache/iceberg/iceberg-spark-runtime-${SPARK_VERSION}_${SCALA_VERSION}/${ICEBERG_VERSION}/${ICEBERG_JAR}" \
         -o "jars/${ICEBERG_JAR}"
    echo "   ✅ $ICEBERG_JAR indirildi"
fi

# 2. AWS Java SDK Bundle
echo -e "\n📥 AWS Java SDK Bundle indiriliyor..."
AWS_JAR="aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar"
if [ -f "jars/$AWS_JAR" ]; then
    echo "   ✅ $AWS_JAR mevcut"
else
    curl -L "${MAVEN_URL}/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_VERSION}/${AWS_JAR}" \
         -o "jars/${AWS_JAR}"
    echo "   ✅ $AWS_JAR indirildi"
fi

# 3. Hadoop AWS
echo -e "\n📥 Hadoop AWS indiriliyor..."
HADOOP_JAR="hadoop-aws-${HADOOP_VERSION}.jar"
if [ -f "jars/$HADOOP_JAR" ]; then
    echo "   ✅ $HADOOP_JAR mevcut"
else
    curl -L "${MAVEN_URL}/org/apache/hadoop/hadoop-aws/${HADOOP_VERSION}/${HADOOP_JAR}" \
         -o "jars/${HADOOP_JAR}"
    echo "   ✅ $HADOOP_JAR indirildi"
fi

echo -e "\n=========================================="
echo "✅ Tüm JAR dosyaları hazır!"
echo "=========================================="
echo ""
echo "📋 İndirilen dosyalar:"
ls -lh jars/
echo ""

pipeline {
    agent any

    environment {
        // Docker Hub 仓库名称 — 按你的实际 Docker Hub 用户名修改
        DOCKER_IMAGE = 'kabukimonosakura/student-productivity-agent'
        // 使用 Jenkins 构建编号作为镜像 Tag
        DOCKER_TAG   = "${env.BUILD_NUMBER}"
    }

    stages {
        // 第一阶段：拉取代码
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        // 第二阶段：安装依赖
        stage('Install Dependencies') {
            steps {
                sh 'pip install -r requirements.txt -r requirements-dev.txt lizard'
            }
        }

        // 第三阶段：代码风格检查 (Linter)
        stage('Lint') {
            steps {
                sh 'mkdir -p reports'
                // Black 格式检查（失败不中断流水线，结果归档查看）
                sh 'black --check . 2>&1 | tee reports/black.log || true'
                // Flake8 静态分析
                sh 'flake8 . 2>&1 | tee reports/flake8.log || true'
            }
        }

        // 第四阶段：运行测试并生成报告
        stage('Test') {
            steps {
                sh '''python -m pytest tests/ \
                    --cov=backend \
                    --cov-report=xml:reports/coverage.xml \
                    --cov-report=term:reports/coverage-term.txt \
                    --cov-report=html:reports/coverage-html \
                    --junitxml=reports/junit.xml \
                    -v 2>&1 | tee reports/test-output.log'''
            }
        }

        // 第五阶段：生成项目指标报告 (LOC, CC, 依赖数等)
        stage('Metrics & Documentation') {
            steps {
                sh 'python scripts/generate_metrics.py'
            }
        }

        // 第六阶段：构建 Docker 镜像
        stage('Build Docker Image') {
            steps {
                sh "docker build -t ${DOCKER_IMAGE}:${DOCKER_TAG} -t ${DOCKER_IMAGE}:latest ."
            }
        }

        // 第七阶段：推送镜像到 Docker Hub
        stage('Push to Docker Hub') {
            steps {
                // 使用 withCredentials 安全传递凭据，避免密码泄露
                withCredentials([usernamePassword(
                    credentialsId: 'docker-hub-credentials',
                    usernameVariable: 'DOCKER_USR',
                    passwordVariable: 'DOCKER_PSW'
                )]) {
                    sh 'echo $DOCKER_PSW | docker login -u $DOCKER_USR --password-stdin'
                }
                // 推送带构建编号的版本
                sh "docker push ${DOCKER_IMAGE}:${DOCKER_TAG}"
                // 同时推送 latest 标签
                sh "docker push ${DOCKER_IMAGE}:latest"
            }
        }
    }

    post {
        always {
            // 归档所有报告文件，构建完成后可在 Jenkins 页面下载查看
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
        }
        failure {
            echo 'Build failed!'
        }
        success {
            echo 'Build succeeded!'
        }
    }
}

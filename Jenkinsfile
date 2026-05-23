pipeline {
    agent any

    environment {
        DOCKER_IMAGE = 'kabukimonosakura/student-productivity-agent'
        DOCKER_TAG   = "${env.BUILD_NUMBER}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    export PATH="/c/Users/25380/anaconda3/envs/software-engineering:/c/Users/25380/anaconda3/envs/software-engineering/Scripts:/c/Users/25380/anaconda3/envs/software-engineering/Library/bin:$PATH"
                    echo "Using Python: $(which python)"
                    python --version
                    pip install -r requirements-dev.txt lizard
                '''
            }
        }

        stage('Lint') {
            steps {
                sh '''
                    export PATH="/c/Users/25380/anaconda3/envs/software-engineering:/c/Users/25380/anaconda3/envs/software-engineering/Scripts:/c/Users/25380/anaconda3/envs/software-engineering/Library/bin:$PATH"
                    mkdir -p reports
                    black --check . 2>&1 | tee reports/black.log || true
                    flake8 . 2>&1 | tee reports/flake8.log || true
                '''
            }
        }

        stage('Test') {
            steps {
                sh '''
                    export PATH="/c/Users/25380/anaconda3/envs/software-engineering:/c/Users/25380/anaconda3/envs/software-engineering/Scripts:/c/Users/25380/anaconda3/envs/software-engineering/Library/bin:$PATH"
                    python -m pytest tests/ \
                        --cov=backend \
                        --cov-report=xml:reports/coverage.xml \
                        --cov-report=term:reports/coverage-term.txt \
                        --cov-report=html:reports/coverage-html \
                        --junitxml=reports/junit.xml \
                        -v 2>&1 | tee reports/test-output.log
                '''
            }
        }

        stage('Metrics & Documentation') {
            steps {
                sh '''
                    export PATH="/c/Users/25380/anaconda3/envs/software-engineering:/c/Users/25380/anaconda3/envs/software-engineering/Scripts:/c/Users/25380/anaconda3/envs/software-engineering/Library/bin:$PATH"
                    python scripts/generate_metrics.py
                '''
            }
        }

        stage('Build Docker Image') {
            steps {
                sh "docker build -t ${DOCKER_IMAGE}:${DOCKER_TAG} -t ${DOCKER_IMAGE}:latest ."
            }
        }

        stage('Push to Docker Hub') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'docker-hub-credentials',
                    usernameVariable: 'DOCKER_USR',
                    passwordVariable: 'DOCKER_PSW'
                )]) {
                    sh 'echo $DOCKER_PSW | docker login -u $DOCKER_USR --password-stdin'
                }
                sh "docker push ${DOCKER_IMAGE}:${DOCKER_TAG}"
                sh "docker push ${DOCKER_IMAGE}:latest"
            }
        }
    }

    post {
        always {
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

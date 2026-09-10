// Upload functionality for attendance data
class AttendanceUploader {
    constructor() {
        this.initializeElements();
        this.bindEvents();
        this.uploadedData = null;
    }

    initializeElements() {
        // Form elements
        this.uploadForm = document.getElementById('uploadForm');
        this.fileInput = document.getElementById('fileInput');
        this.uploadBtn = document.getElementById('uploadBtn');
        this.downloadTemplateBtn = document.getElementById('downloadTemplate');
        
        // Info elements
        this.fileInfo = document.getElementById('fileInfo');
        this.fileName = document.getElementById('fileName');
        this.fileSize = document.getElementById('fileSize');
        
        // Progress elements
        this.progressSection = document.getElementById('progressSection');
        this.progressFill = document.getElementById('progressFill');
        this.progressText = document.getElementById('progressText');
        
        // Result elements
        this.resultSection = document.getElementById('resultSection');
        this.resultHeader = document.getElementById('resultHeader');
        this.resultTitle = document.getElementById('resultTitle');
        this.resultStats = document.getElementById('resultStats');
        this.resultMessage = document.getElementById('resultMessage');
        this.errorsSection = document.getElementById('errorsSection');
        this.errorsList = document.getElementById('errorsList');
        
        // Preview elements
        this.dataPreview = document.getElementById('dataPreview');
        this.previewCount = document.getElementById('previewCount');
        this.dataTable = document.getElementById('dataTable');
        this.tableHead = document.getElementById('tableHead');
        this.tableBody = document.getElementById('tableBody');
        
        // Action elements
        this.actionsSection = document.getElementById('actionsSection');
        this.uploadAnotherBtn = document.getElementById('uploadAnother');
        this.saveDataBtn = document.getElementById('saveData');
    }

    bindEvents() {
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        this.uploadForm.addEventListener('submit', (e) => this.handleUpload(e));
        this.downloadTemplateBtn.addEventListener('click', () => this.downloadTemplate());
        this.uploadAnotherBtn.addEventListener('click', () => this.resetForm());
        this.saveDataBtn.addEventListener('click', () => this.saveToDatabase());
    }

    handleFileSelect(event) {
        const file = event.target.files[0];
        
        if (file) {
            // Validate file type
            const validTypes = ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                              'application/vnd.ms-excel', 'text/csv', 'application/csv'];
            const validExtensions = ['xlsx', 'xls', 'csv'];
            const fileExtension = file.name.split('.').pop().toLowerCase();
            
            if (!validTypes.includes(file.type) && !validExtensions.includes(fileExtension)) {
                this.showError('Please select a valid Excel (.xlsx, .xls) or CSV (.csv) file.');
                this.resetFileInput();
                return;
            }
            
            // Show file info
            this.fileName.textContent = file.name;
            this.fileSize.textContent = this.formatFileSize(file.size);
            this.fileInfo.style.display = 'flex';
            this.uploadBtn.disabled = false;
            
            // Hide previous results
            this.hideResults();
        } else {
            this.resetFileInput();
        }
    }

    async handleUpload(event) {
        event.preventDefault();
        
        const file = this.fileInput.files[0];
        if (!file) {
            this.showError('Please select a file first.');
            return;
        }
        
        this.showProgress();
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            
            const response = await fetch('/upload/attendance', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.uploadedData = result.data;
                this.showSuccess(result.message, result.records_processed || 0);
                // Don't call showResults for successful uploads, showSuccess is enough
            } else {
                this.showError(result.message, result.error);
            }
            
        } catch (error) {
            this.showError('Upload failed', `Network error: ${error.message}`);
        } finally {
            this.hideProgress();
        }
    }

    async downloadTemplate() {
        try {
            const response = await fetch('/upload/template');
            
            if (!response.ok) {
                throw new Error('Failed to download template');
            }
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'attendance_template.xlsx';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
        } catch (error) {
            this.showError(`Failed to download template: ${error.message}`);
        }
    }

    showProgress() {
        this.progressSection.style.display = 'block';
        this.uploadBtn.disabled = true;
        this.progressText.textContent = 'Uploading file...';
        
        // Simulate progress
        let progress = 0;
        const interval = setInterval(() => {
            progress += Math.random() * 30;
            if (progress > 90) progress = 90;
            this.progressFill.style.width = `${progress}%`;
            
            if (progress > 30) this.progressText.textContent = 'Processing data...';
            if (progress > 60) this.progressText.textContent = 'Validating records...';
        }, 200);
        
        this.progressInterval = interval;
    }

    hideProgress() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
        }
        this.progressFill.style.width = '100%';
        setTimeout(() => {
            this.progressSection.style.display = 'none';
            this.uploadBtn.disabled = false;
        }, 500);
    }

    showResults(result) {
        // Show result section
        this.resultSection.style.display = 'block';
        
        // Set title and stats
        if (result.success) {
            this.resultTitle.innerHTML = '✅ Upload Successful';
            this.resultHeader.className = 'result-header success';
        } else {
            this.resultTitle.innerHTML = '❌ Upload Failed';
            this.resultHeader.className = 'result-header error';
        }
        
        // Show statistics
        this.resultStats.innerHTML = `
            <div class="stat">
                <span class="stat-label">Total Records:</span>
                <span class="stat-value">${result.total_records}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Processed:</span>
                <span class="stat-value">${result.processed_records}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Errors:</span>
                <span class="stat-value">${result.error_count}</span>
            </div>
        `;
        
        // Show message
        this.resultMessage.textContent = result.message;
        
        // Show errors if any
        if (result.errors && result.errors.length > 0) {
            this.showErrors(result.errors);
        }
        
        // Show data preview if successful
        if (result.success && result.records && result.records.length > 0) {
            this.showDataPreview(result.records);
            this.actionsSection.style.display = 'block';
        }
    }

    showErrors(errors) {
        this.errorsSection.style.display = 'block';
        this.errorsList.innerHTML = '';
        
        errors.forEach(error => {
            const errorItem = document.createElement('div');
            errorItem.className = 'error-item';
            errorItem.innerHTML = `
                <div class="error-row">Row ${error.row}</div>
                <div class="error-message">${error.error}</div>
            `;
            this.errorsList.appendChild(errorItem);
        });
    }

    showDataPreview(records) {
        this.dataPreview.style.display = 'block';
        this.previewCount.textContent = `Showing ${Math.min(records.length, 10)} of ${records.length} records`;
        
        // Create table headers
        const headers = ['No', 'DN', 'UID', 'Name', 'Status', 'Action', 'APB', 'Job Code', 'Date Time'];
        this.tableHead.innerHTML = `
            <tr>
                ${headers.map(header => `<th>${header}</th>`).join('')}
            </tr>
        `;
        
        // Create table rows (show first 10 records)
        this.tableBody.innerHTML = '';
        const previewRecords = records.slice(0, 10);
        
        previewRecords.forEach(record => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${record.no}</td>
                <td>${record.dn}</td>
                <td>${record.uid}</td>
                <td>${record.name}</td>
                <td><span class="status-badge ${record.status.toLowerCase()}">${record.status}</span></td>
                <td>${record.action}</td>
                <td>${record.apb}</td>
                <td>${record.job_code}</td>
                <td>${new Date(record.date_time).toLocaleString()}</td>
            `;
            this.tableBody.appendChild(row);
        });
    }

    saveToDatabase() {
        // This would typically send the data to a save endpoint
        // For now, we'll just show a success message
        alert('Data saved to database successfully! (This is a demo - implement actual save functionality)');
    }

    resetForm() {
        this.uploadForm.reset();
        this.resetFileInput();
        this.hideResults();
        this.uploadedData = null;
    }

    resetFileInput() {
        this.fileInfo.style.display = 'none';
        this.uploadBtn.disabled = true;
    }

    hideResults() {
        this.resultSection.style.display = 'none';
        this.errorsSection.style.display = 'none';
        this.dataPreview.style.display = 'none';
        this.actionsSection.style.display = 'none';
    }

    showError(message, details = null) {
        let errorMsg = `❌ ${message}`;
        if (details) {
            errorMsg += `\n\nDetails: ${details}`;
        }
        alert(errorMsg);
    }

    showSuccess(message, recordCount = 0) {
        let successMsg = `✅ ${message}`;
        if (recordCount > 0) {
            successMsg += `\n\nRecords processed: ${recordCount}`;
        }
        alert(successMsg);
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
}

// Initialize the uploader when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new AttendanceUploader();
});
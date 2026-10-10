import { Component } from '@angular/core';
import { NextComponent } from '../components/next.component';
@Component({standalone:true,imports:[NextComponent],template:`<header class="page-heading"><div><h1>Know what comes next<span>.</span></h1><p>Keep your exam sequence and next steps in one place.</p></div></header><app-next [detailed]="true" />`})
export class ExamsComponent {}

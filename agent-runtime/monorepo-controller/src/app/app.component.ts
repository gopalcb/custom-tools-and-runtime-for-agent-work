import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { HeaderComponent } from './components/header/header.component';

@Component({ selector: 'app-root', standalone: true, imports: [RouterOutlet, HeaderComponent], template: `
  <div class="app-page"><app-header /><main class="workspace"><router-outlet /></main></div>
`, styles: [`
  :host { display:block; min-height:100vh; } .app-page { min-height:100vh; display:grid; grid-template-rows:54px 1fr; }
  .workspace { min-width:0; min-height:0; padding:10px 18px 18px; }
  @media (max-width: 700px) { .workspace { padding:10px; } }
`] })
export class AppComponent {}
